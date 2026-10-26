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

// old path (no leading slash, trailing slash) -> new path.
//
// Only posts that still exist are listed. Nine legacy URLs pointed at
// content that was deliberately deleted (empty stubs, copied reference
// material, obsolete Jekyll notes); those now 404, which is the honest
// signal for removed content. Point them at /archives/ instead if you
// would rather give old bookmarks a soft landing.
const REDIRECTS = {
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
