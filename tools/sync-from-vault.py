#!/usr/bin/env python3
"""sync-from-vault.py — 把 notes vault 的 blog/ 成稿同步到本站 source/_posts/

用法（在 nameyule.github.io 目录下执行）:
    python3 tools/sync-from-vault.py --dry-run   # 只看会做什么
    python3 tools/sync-from-vault.py             # 写入 source/_posts/
    python3 tools/sync-from-vault.py --check     # 自检：有差异就退出码 1
    python3 tools/sync-from-vault.py --prune     # 删掉 vault 里已不存在的同步产物

约定
----
源    <VAULT>/blog/<domain>/*.md        domain = 知识领域 7 个 + fmcginfo
目标  source/_posts/<domain>/<slug>.md

* **全部子目录都是站点分类**，目录名直接变分类名。fmcginfo 只是其中一个，
  额外要发公众号（那一步在这个仓库之外）。
* 跳过 README.md / index.md / log.md / manifest.json 和点开头的目录（blog/.drafts/）。
* URL 由 slug 决定（permalink: posts/:name/，:name = 去扩展名的文件名，分类目录不进 URL）。
* slug 取值顺序：frontmatter 的 `slug` → 文件名（已是合法 ASCII kebab 就直接用）。
  都不行就报错，**不猜、不转拼音**——URL 是长期资产。
* 日期取值顺序：frontmatter 的 `published`/`date` → 文件名的 YYYY-MM-DD 前缀
  → 正文的 `> Published: YYYY-MM-DD`。
* 标题取值顺序：frontmatter 的 `title` → 正文首个 `# 标题`（用掉就从正文删掉，
  免得和主题渲染的标题重复）。
* **转载不上线。** 带 `legacy` 标签的默认跳过；`publish_web: false` 可显式挡掉，
  没有 frontmatter 的 wiki 格式成稿在正文写一行 `> publish_web: false` 也行。
* 成稿里指向 vault 私有文件的 `.md` 相对链接，会退化成纯文本（留引述不留死链）；
  指向**同样已发布**成稿的链接会改写成 `/posts/<slug>/` 站内地址。
* 生成的文件带 `synced_from:` 标记；--prune **只删**带这个标记的文件，
  手写的旧文章永远不会被动到。
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("需要 PyYAML：pip3 install pyyaml")

SITE_ROOT = Path(__file__).resolve().parent.parent  # tools/ 的上一级 = 仓库根
# vault 路径可由发布链路经环境变量传入（publish-blog-post 的 .env 配置），默认保持原路径
VAULT_ROOT = Path(os.environ.get("NOTES_VAULT_DIR", "/Users/huyuhui/notes"))
POSTS_DIR = SITE_ROOT / "source" / "_posts"
BLOG_DIR = VAULT_ROOT / "blog"

# blog/ 下允许的目录，与 vault 的 check_vault.py 保持一致
DOMAINS = {"ai-tech", "product", "work", "investment", "tools", "sources", "film"}
PROJECTS = {"fmcginfo"}
KNOWN_DIRS = DOMAINS | PROJECTS

# 这些是目录级说明文件，不是成稿
SKIP_NAMES = {"readme.md", "manifest.json", "index.md", "log.md"}

# vault 用这些标签记状态，不该出现在站点标签云里
BOOKKEEPING_TAGS = {"published", "legacy", "ingested", "style-sample", "voice", "draft"}

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)
PUBLISHED_RE = re.compile(r"^>\s*Published:\s*(\d{4}-\d{2}-\d{2})", re.M)

# 生成文件里标记「这文件是同步来的」，--prune 靠它区分手写文章
MARKER_KEY = "synced_from"

REQUIRED_PY = (3, 9)


class SyncError(Exception):
    """一条成稿不合格，不能同步。"""


class SkipPost(Exception):
    """这条成稿不该上线，安静跳过（不是错误）。"""


# ---------------------------------------------------------------- 解析

def split_frontmatter(text: str) -> tuple[dict, str]:
    """拆成 (frontmatter, 正文)。没有 frontmatter 是合法的——返回空 dict。

    vault 有两种成稿格式：
      * fmcginfo 用 YAML frontmatter
      * 七个知识领域沿用 wiki 格式（# 标题 + > Sources:），没有 frontmatter
    两种都要能发。
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text          # 开头看着像 --- 但没闭合，当正文处理
    raw = text[3:end].strip("\n")
    try:
        meta = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise SyncError(f"frontmatter 不是合法 YAML：{exc}") from exc
    if not isinstance(meta, dict):
        raise SyncError("frontmatter 顶层必须是键值对")
    body = text[end + 4:]
    return meta, body.lstrip("\n")


def pick_title(meta: dict, body: str, filename: str) -> tuple[str, str]:
    """返回 (标题, 去掉标题行之后的正文)。"""
    title = str(meta.get("title") or "").strip()
    if title:
        return title, body

    m = H1_RE.search(body)
    if m:
        # 标题被主题单独渲染，正文里再留一行 # 标题 就重复了
        return m.group(1).strip(), (body[:m.start()] + body[m.end():]).lstrip("\n")

    raise SyncError(
        f"定不出标题：frontmatter 没有 title，正文也没有 `# 标题`（对应 {filename}）"
    )


def pick_date(meta: dict, body: str, filename: str) -> dt.datetime:
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

    m = DATE_PREFIX_RE.match(filename)
    if m:
        return dt.datetime.strptime(m.group(1), "%Y-%m-%d")

    m = PUBLISHED_RE.search(body)
    if m:
        return dt.datetime.strptime(m.group(1), "%Y-%m-%d")

    raise SyncError(
        "定不出发布日期。三处任选其一：\n"
        "       frontmatter 写 `published: YYYY-MM-DD`\n"
        "       文件名用 `YYYY-MM-DD-标题.md` 前缀\n"
        "       正文写 `> Published: YYYY-MM-DD`"
    )


def pick_slug(meta: dict, filename: str) -> str:
    """slug = 显式 frontmatter 字段，或已经是合法 kebab 的文件名。"""
    slug = str(meta.get("slug") or "").strip()
    if not slug:
        stem = Path(filename).stem
        if SLUG_RE.match(stem):
            return stem          # 文件名本身就是个好 slug，不用再写一遍
        raise SyncError(
            "缺 slug 字段。URL 由 slug 决定，中文文件名会变成百分号编码的一长串。\n"
            f"       请在 frontmatter 加一行：  slug: <ascii-kebab-case>\n"
            f"       （对应 {filename}）"
        )
    if not SLUG_RE.match(slug):
        raise SyncError(f"slug {slug!r} 不合法：只允许小写字母、数字、中划线，如 boss-three-things")
    return slug


def pick_tags(meta: dict) -> list[str]:
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return [str(t).strip() for t in tags if str(t).strip() and str(t).strip() not in BOOKKEEPING_TAGS]


BODY_OPT_OUT_RE = re.compile(r"^>\s*publish_web\s*:\s*false\s*$", re.I | re.M)

# [文字](路径.md)，但不吃图片 ![文字](路径) —— 那是另一种东西
MD_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+\.md)(?:#[^)]*)?\)")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")

# 生成的图片统一放 source/images/blog/<分类>/<成稿名>/，和手管的 avatar/logo 分开
IMG_ROOT = SITE_ROOT / "source" / "images" / "blog"


def publication_blocker(meta: dict, body: str) -> str | None:
    """返回阻止上线的原因；None 表示可以上线。

    三条规则都服务于「只放原创」：
      publish_web: false       显式挡掉，作者自己关的
      legacy 标签              转载存档，天生不上线
      > publish_web: false     同上，给没有 frontmatter 的 wiki 格式成稿用
    """
    if meta.get("publish_web") is False:
        return "frontmatter 写了 publish_web: false"

    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    if "legacy" in {str(t).strip().lower() for t in tags}:
        return "带 legacy 标签（转载存档，不上线）"

    if BODY_OPT_OUT_RE.search(body):
        return "正文写了 > publish_web: false"
    return None


# ---------------------------------------------------------------- 生成

def asset_urls(src: Path, domain: str) -> dict[str, str]:
    """本地附件 -> 站点 URL。

    库的约定是「文档的本地附件放在同级 assets/<md文件名去掉扩展名>/<附件名>」，
    正文里按相对路径引。搬到站点后地址变了，得跟着改写，否则图就是个裂开的框。
    """
    root = src.parent / "assets" / src.stem
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for f in sorted(root.rglob("*")):
        if f.is_file():
            rel = f.relative_to(src.parent).as_posix()          # assets/<stem>/<名>
            sub = f.relative_to(root).as_posix()                # <名>（可带子目录）
            out[rel] = f"/images/blog/{domain}/{src.stem}/{sub}"
    return out


def rewrite_images(body: str, src: Path, domain: str) -> str:
    """把指向本地附件的图片改成站点地址；远程图和 data: 原样不动。

    引了但文件不在本地的，保持原样并由调用方警告——总比悄悄删掉图强。
    """
    mapping = asset_urls(src, domain)

    def repl(m: re.Match) -> str:
        alt, target = m.group(1), m.group(2)
        if target.startswith(("http://", "https://", "data:")):
            return m.group(0)
        key = re.sub(r"^(\./)+", "", target)
        return f"![{alt}]({mapping[key]})" if key in mapping else m.group(0)

    return IMAGE_RE.sub(repl, body)


def copy_assets(src: Path, domain: str) -> int:
    """把成稿的本地附件复制到站点，返回复制的文件数。"""
    root = src.parent / "assets" / src.stem
    if not root.is_dir():
        return 0
    dest_root = IMG_ROOT / domain / src.stem
    n = 0
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        dest = dest_root / f.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        n += 1
    return n


def rewrite_links(body: str, src: Path, slug_map: dict[Path, str]) -> str:
    """把 vault 内部链接改写成站点能用的东西。

    blog/ 成稿开头要列出它依据的 wiki 文章（vault README 的约定），wiki 里还有
    指向 raw/ 的相对链接。这些 .md 在站点上并不存在，直接发出去就是一片死链。

      * 目标也是已发布的 blog 成稿  ->  [标题](/posts/<slug>/)，变成真能点的站内链接
      * 目标是 vault 私有文件        ->  退化成纯文本「标题」，留引述不留死链
      * 外链 / 非 .md                ->  原样不动
    """
    def repl(m: re.Match) -> str:
        label, target = m.group(1), m.group(2)
        resolved = (src.parent / target).resolve()
        slug = slug_map.get(resolved)
        return f"[{label}](/posts/{slug}/)" if slug else label

    return MD_LINK_RE.sub(repl, body)


def render_post(src: Path, domain: str, slug_map: dict[Path, str] | None = None) -> tuple[str, str]:
    """返回 (slug, 渲染好的 hexo 文章全文)。"""
    meta, body = split_frontmatter(src.read_text(encoding="utf-8"))

    blocker = publication_blocker(meta, body)
    if blocker:
        raise SkipPost(blocker)

    title, body = pick_title(meta, body, src.name)
    slug = pick_slug(meta, src.name)
    date = pick_date(meta, body, src.name)
    tags = pick_tags(meta)
    if slug_map:
        body = rewrite_links(body, src, slug_map)
    body = rewrite_images(body, src, domain)

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
            if md.name.lower() in SKIP_NAMES:
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

    # 成稿没了，它的图片目录也该跟着走。手管的 avatar/logo 在 source/images/ 下，
    # 不在 images/blog/ 里，永远不会被扫到。
    if IMG_ROOT.is_dir():
        for imgdir in sorted(IMG_ROOT.glob("*/*")):
            if not imgdir.is_dir():
                continue
            domain, stem = imgdir.parent.name, imgdir.name
            if (BLOG_DIR / domain / f"{stem}.md").exists():
                continue
            print(f"  - 删除 {imgdir.relative_to(SITE_ROOT)}/（成稿已不在 vault）")
            if not dry_run:
                shutil.rmtree(imgdir)
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

    # 先跑一遍拿 slug 映射，第二遍才能把跨文章链接改写成站内地址
    slug_map: dict[Path, str] = {}
    for domain, src in entries:
        try:
            slug_map[src.resolve()] = render_post(src, domain)[0]
        except (SyncError, SkipPost):
            continue

    written = changed = skipped = held = 0
    errors: list[str] = []
    seen_slugs: dict[str, str] = {}

    for domain, src in entries:
        rel = src.relative_to(VAULT_ROOT)

        try:
            slug, text = render_post(src, domain, slug_map)
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

        # 引用了本地图片但文件不在 assets/<成稿名>/ 里的，点出来——图会显示成裂框。
        # 必须拿**改写前**的正文查：text 已经是站点地址了，拿它查键查不中。
        known = set(asset_urls(src, domain))
        raw_body = split_frontmatter(src.read_text(encoding="utf-8"))[1]
        for m in IMAGE_RE.finditer(raw_body):
            target = re.sub(r"^(\./)+", "", m.group(2))
            if target.startswith(("http://", "https://", "data:")):
                continue
            if target not in known:
                print(f"  ! {rel} 引用了本地图片 {target}，但在 assets/{src.stem}/ 里找不到", file=sys.stderr)

        action = "新增" if current is None else "更新"
        print(f"  ~ {rel} -> source/_posts/{domain}/{slug}.md（{action}）")
        if not dry_run:
            dest.write_text(text, encoding="utf-8")
            n_img = copy_assets(src, domain)
        else:
            n_img = len(known)
        changed += 1
        written += 1
        if n_img:
            print(f"      + {n_img} 个附件 -> source/images/blog/{domain}/{src.stem}/")

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
