/**
 * Legacy URL redirects.
 *
 * The pre-2026 permalink scheme was `:year/:month/:day/:title/`, and because
 * `:title` folds the directory path into the slug, URLs looked like
 * `/2020/07/13/tech-coding-2020-07-14-Develop-with-Linux/` — date repeated,
 * category folders leaking into the slug, and the date segment itself off by
 * one (the old site was built on a US-timezone machine).
 *
 * GitHub Pages serves static files only, so there is no real 301 here. Each
 * stub instead combines the three signals static hosts can give:
 *   - `rel=canonical`  tells crawlers where the content now lives
 *   - meta refresh 0   is treated as a redirect by search engines
 *   - location.replace moves the browser without polluting history
 */
'use strict';

const SITE_URL = 'https://hyh.im';

// old path (no leading slash, trailing slash) -> new path
const REDIRECTS = {
  '2018/07/04/tech-coding-2018-07-05-SOA-SOAP-REST/': '/posts/soa-soap-rest/',
  '2018/07/04/tech-coding-2018-07-07-Web-APIs/': '/posts/web-apis/',
  '2020/07/13/career-manage-2020-08-28-Docs-in-Projects/': '/posts/agile-docs/',
  '2020/07/13/tech-coding-2020-07-14-Develop-with-Linux/': '/posts/linux-dev-environment/',
  '2020/07/13/tech-coding-2020-07-14-Github-pages-jekyll/': '/posts/github-pages-jekyll/',
  '2020/07/13/tech-coding-2020-08-27-markdown/': '/posts/markdown-tips/',
  '2020/07/13/tech-os-2020-07-14-Vscode-ssh-linux/': '/posts/vscode-remote-ssh/',
  '2020/08/31/life-twentyyears-graduate/': '/posts/graduate/',
  '2020/09/06/career-new/': '/posts/career-new/',
  '2020/09/06/career-when-you-should-change-your-job/': '/posts/when-to-change-job/',
  '2020/09/06/read-the-four-steps-to-the-epiphany/': '/posts/four-steps-to-the-epiphany/'
};

function stub(from, to) {
  const absolute = SITE_URL + to;
  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>页面已迁移</title>
<link rel="canonical" href="${absolute}">
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url=${to}">
</head>
<body>
<p>页面已迁移至 <a href="${to}">${absolute}</a>，正在跳转……</p>
<script>location.replace(${JSON.stringify(to)});</script>
</body>
</html>
`;
}

hexo.extend.generator.register('legacy-redirects', function () {
  return Object.keys(REDIRECTS).map((from) => ({
    path: from + 'index.html',
    data: stub(from, REDIRECTS[from])
  }));
});
