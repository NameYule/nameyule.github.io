#!/usr/bin/env python3
"""sync-from-vault.py — 把 notes vault 的 blog/ 成稿同步到本站 source/_posts/

用法（在 nameyule.github.io 目录下执行）:
    python3 tools/sync-from-vault.py --dry-run   # 只看会做什么
    python3 tools/sync-from-vault.py             # 写入 source/_posts/
    python3 tools/sync-from-vault.py --check     # CI/自检：有差异就退出码 1
    python3 tools/sync-from-vault.py --prune     # 额外删掉 vault 里已不存在的同步产物

约定
----
源    <VAULT>/blog/<domain>/*.md        domain = 知识领域 7 个 + fmcginfo
目标  source/_posts/<domain>/<slug>.md

* 只收 `YYYY-MM-DD-*.md` 成稿。README.md、manifest.json、点开头的目录/文件一律跳过
  （blog/.drafts/ 就是这么被挡在外面的）。
* URL 由**文件名**决定：_config.yml 是 permalink: posts/:name/，:name = 去扩展名的文件名，
  分类目录不会进 URL。所以 slug 必须是 ASCII——中文文件名会变成百分号编码的一长串。
* slug 来自成稿 frontmatter 的 `slug:` 字段，本脚本不猜、不转拼音。
* **转载不上线。** 带 `legacy` 标签的成稿（重启前转载存档）默认跳过；
  任何成稿也可用 `publish_web: false` 显式挡掉。这是「只放原创」约束的机器兜底。
* 生成的文件带 `synced_from:` 标记；--prune **只删**带这个标记的文件，
  手写的旧文章（when-to-change-job.md 之类）永远不会被动到。
* 本站文章是手写资产，本脚本只做单向 vault -> 站点 的搬运，不回写 vault。
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("需要 PyYAML：pip3 install pyyaml")

SITE_ROOT = Path(__file__).resolve().parent.parent  # tools/ 的上一级 = 仓库根
VAULT_ROOT = Path("/Users/huyuhui/notes")
POSTS_DIR = SITE_ROOT / "source" / "_posts"
BLOG_DIR = VAULT_ROOT / "blog"

# blog/ 下允许的目录，与 vault 的 check_vault.py 保持一致
DOMAINS = {"ai-tech", "product", "work", "investment", "tools", "sources", "film"}
PROJECTS = {"fmcginfo"}
KNOWN_DIRS = DOMAINS | PROJECTS

# vault 用这些标签记状态，不该出现在站点标签云里
BOOKKEEPING_TAGS = {"published", "legacy", "ingested", "style-sample", "voice", "draft"}

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")

# 生成文件里标记「这文件是同步来的」，--prune 靠它区分手写文章
MARKER_KEY = "synced_from"

REQUIRED_PY = (3, 9)


class SyncError(Exception):
    """一条成稿不合格，不能同步。"""


class SkipPost(Exception):
    """这条成稿不该上线，安静跳过（不是错误）。"""


# ---------------------------------------------------------------- 解析

def split_frontmatter(text: str) -> tuple[dict, str]:
    """把一篇成稿拆成 (frontmatter dict, 正文)。没有 frontmatter 就报错。"""
    if not text.startswith("---"):
        raise SyncError("缺少 YAML frontmatter（--- 开头的那段元数据）")
    end = text.find("\n---", 3)
    if end == -1:
        raise SyncError("frontmatter 没有闭合的 ---")
    raw = text[3:end].strip("\n")
    body = text[end + 4:]
    if body.startswith("\n"):
        body = body[1:]
    try:
        meta = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise SyncError(f"frontmatter 不是合法 YAML：{exc}") from exc
    if not isinstance(meta, dict):
        raise SyncError("frontmatter 顶层必须是键值对")
    return meta, body


def pick_date(meta: dict, filename: str) -> dt.datetime:
    """日期取 frontmatter 的 published / date，否则取文件名前缀。"""
    for key in ("published", "date"):
        value = meta.get(key)
        if value is None:
            continue
        if isinstance(value, dt.datetime):
            return value
        if isinstance(value, dt.date):
            return dt.datetime(value.year, value.month, value.day, 12, 0, 0)
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
            try:
                return dt.datetime.strptime(text, fmt)
            except ValueError:
                continue
        raise SyncError(f"{key}: 认不出日期 {value!r}，请写成 YYYY-MM-DD")

    match = DATE_PREFIX_RE.match(filename)
    if match:
        return dt.datetime.strptime(match.group(1), "%Y-%m-%d")
    raise SyncError("定不出发布日期：frontmatter 没有 published/date，文件名也没有 YYYY-MM-DD 前缀")


def pick_slug(meta: dict, filename: str) -> str:
    """slug 必须显式写在 frontmatter 里，且是 ASCII。"""
    slug = str(meta.get("slug") or "").strip()
    if not slug:
        hint = filename.rsplit("/", 1)[-1]
        raise SyncError(
            "缺 slug 字段。URL 由文件名决定，中文文件名会变成百分号编码的 URL。\n"
            f"       请在 frontmatter 加一行：  slug: <ascii-kebab-case>\n"
            f"       （对应 {hint}）"
        )
    if not SLUG_RE.match(slug):
        raise SyncError(f"slug {slug!r} 不合法：只允许小写字母、数字、中划线，如 lanyueliang-2015")
    return slug


def pick_tags(meta: dict) -> list[str]:
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return [str(t).strip() for t in tags if str(t).strip() and str(t).strip() not in BOOKKEEPING_TAGS]


def publication_blocker(meta: dict) -> str | None:
    """返回阻止上线的原因；None 表示可以上线。

    两条规则都服务于 blog/ 的约束二「只放原创」：
      publish_web: false  显式挡掉，作者自己关的
      legacy 标签         重启前转载存档，天生不上线
    """
    if meta.get("publish_web") is False:
        return "frontmatter 写了 publish_web: false"

    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    if "legacy" in {str(t).strip().lower() for t in tags}:
        return "带 legacy 标签（重启前转载存档，不上线）"
    return None


def pick_title(meta: dict) -> str:
    title = str(meta.get("title") or "").strip()
    if not title:
        raise SyncError("缺 title 字段")
    return title


# ---------------------------------------------------------------- 生成

def render_post(src: Path, domain: str) -> tuple[str, str]:
    """返回 (slug, 渲染好的 hexo 文章全文)。"""
    meta, body = split_frontmatter(src.read_text(encoding="utf-8"))

    blocker = publication_blocker(meta)
    if blocker:
        raise SkipPost(blocker)

    title = pick_title(meta)
    slug = pick_slug(meta, src.name)
    date = pick_date(meta, src.name)
    tags = pick_tags(meta)

    out_meta: dict = {
        "title": title,
        "date": date.strftime("%Y-%m-%d %H:%M:%S +0800"),
        "categories": [domain],
    }
    if tags:
        out_meta["tags"] = tags
    if meta.get("description"):
        out_meta["description"] = str(meta["description"]).strip()
    if meta.get("source"):
        out_meta["source_url"] = str(meta["source"]).strip()
    out_meta[MARKER_KEY] = f"blog/{domain}/{src.name}"

    dumped = yaml.safe_dump(out_meta, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return slug, f"---\n{dumped}---\n\n{body.rstrip()}\n"


# ---------------------------------------------------------------- 主流程

def collect() -> list[tuple[str, Path]]:
    """扫出所有要同步的成稿，返回 (domain, 路径)。"""
    if not BLOG_DIR.is_dir():
        raise SyncError(f"找不到 vault 的 blog 目录：{BLOG_DIR}")

    found: list[tuple[str, Path]] = []
    for child in sorted(BLOG_DIR.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue  # 跳过 .drafts 之类的点目录
        if child.name not in KNOWN_DIRS:
            print(f"  ! 跳过未知目录 blog/{child.name}/（不在领域白名单里）", file=sys.stderr)
            continue
        for md in sorted(child.glob("*.md")):
            if md.name in {"README.md", "MANIFEST.md"}:
                continue
            if not DATE_PREFIX_RE.match(md.name):
                print(f"  ! 跳过 blog/{child.name}/{md.name}（文件名不是 YYYY-MM-DD-标题.md）", file=sys.stderr)
                continue
            found.append((child.name, md))
    return found


def prune(dry_run: bool) -> int:
    """删掉 vault 里已经不存在的同步产物。只碰带 MARKER_KEY 的文件。"""
    if not POSTS_DIR.is_dir():
        return 0
    living = {f"blog/{d}/{p.name}" for d, p in collect()}
    removed = 0
    for out in sorted(POSTS_DIR.rglob("*.md")):
        try:
            meta, _ = split_frontmatter(out.read_text(encoding="utf-8"))
        except SyncError:
            continue
        marker = meta.get(MARKER_KEY)
        if not marker:
            continue  # 手写文章，不碰
        if marker in living:
            continue
        rel = out.relative_to(SITE_ROOT)
        print(f"  - 删除 {rel}（源 {marker} 已不在 vault）")
        if not dry_run:
            out.unlink()
        removed += 1
    return removed


def main() -> int:
    if sys.version_info[:2] < REQUIRED_PY:
        sys.exit(f"需要 Python {REQUIRED_PY[0]}.{REQUIRED_PY[1]}+")

    parser = argparse.ArgumentParser(description="同步 notes vault 的 blog/ 成稿到 source/_posts/")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    parser.add_argument("--check", action="store_true", help="有不同步就退出码 1，不写文件")
    parser.add_argument("--prune", action="store_true", help="删除 vault 里已不存在的同步产物")
    args = parser.parse_args()
    dry_run = args.dry_run or args.check

    entries = collect()
    print(f"vault 里找到 {len(entries)} 篇成稿")

    written = changed = skipped = held = 0
    errors: list[str] = []
    seen_slugs: dict[str, str] = {}

    for domain, src in entries:
        rel = src.relative_to(VAULT_ROOT)
        try:
            slug, text = render_post(src, domain)
        except SkipPost as exc:
            print(f"  · {rel}（不上线：{exc}）")
            held += 1
            continue
        except SyncError as exc:
            errors.append(f"{rel}: {exc}")
            continue

        # slug 全站唯一，撞了就是 URL 冲突
        if slug in seen_slugs:
            errors.append(f"{rel}: slug {slug!r} 与 {seen_slugs[slug]} 重复")
            continue
        seen_slugs[slug] = str(rel)

        dest = POSTS_DIR / domain / f"{slug}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)

        current = dest.read_text(encoding="utf-8") if dest.exists() else None
        if current == text:
            print(f"  = {rel} -> source/_posts/{domain}/{slug}.md（无变化）")
            skipped += 1
            continue

        action = "新增" if current is None else "更新"
        print(f"  ~ {rel} -> source/_posts/{domain}/{slug}.md（{action}）")
        if not dry_run:
            dest.write_text(text, encoding="utf-8")
        changed += 1
        written += 1

    if args.prune:
        print("\n清理：")
        removed = prune(dry_run)
        if not removed:
            print("  （没有需要清理的）")

    if errors:
        print("\n以下成稿不合格，没有同步：", file=sys.stderr)
        for err in errors:
            print(f"  x {err}", file=sys.stderr)

    print(
        f"\n{'[dry-run] ' if dry_run else ''}{written} 篇{'待' if dry_run else ''}写入，"
        f"{skipped} 篇无变化，{held} 篇按规则不上线，{len(errors)} 篇报错"
    )
    if errors or (args.check and changed):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
