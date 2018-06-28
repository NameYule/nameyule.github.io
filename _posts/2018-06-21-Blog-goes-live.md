---
layout: post
title: "老于乐的博客上线了"
date: 2018-06-21 23:13:00
description: 部落格上线经过；GitHub Pages使用教程
share: true
comments: true
tags:
 - 学习笔记
---


博客兴起已经有10多个年头了吧。以前一直觉得自己实在没发坚持输出一些有用的东西，所以也懒得去弄。

最近看github的时候无意中看到有这么简单的搭建方式，想尝试一下。
正好这段时间学习、阅读等方面都需要做一些记录，所以立马就动手了。

虽然简单，但从无到有，加上本来自己也只是零零碎碎看了一些东西，过程中还是遇到各种困难。

简单记录一下。网上大量教程，细节就略了。

这个博客使用了Jekyll的框架，然后从官方模版库拉了这个性冷淡风格的模版，感觉比较适合我。

**坑1: 模版选择**  
最初看的[教程](https://github.com/litaotao/litaotao.github.io)里面只告诉我直接克隆里面的模版使用，我以为只有一种方式可以选，后来尝试过程中才发现模版本身可以自己定制（[从0开始定制方法看这里](http://www.ruanyifeng.com/blog/2012/08/blogging_with_jekyll.html)），当然网上也有大量现成的可以用，从[这里](https://github.com/jekyll/jekyll/wiki/Themes)挑选。

**坑2: github仓库命名**  
git开通github page的时候，要求建一个仓库，仓库命名有讲究。我开始用github.io命名，也能打开页面，但是就变成https://nameyule.github.io/github.io这样了，不能通过https://nameyule.github.io直接访问。后来才发现，命名必须是“nameyule.github.io”这样（不带引号）。

**坑3: 文章标签**  
文章标签是脚本自动添加的，但是在模版里面，要在头部（官方叫[front matter](https://jekyllrb.com/docs/frontmatter/))定义tag标签，定义的形式类似这样：
```
---
tag: 笔记 
---
```
注意这段内容不能挪位置，必须放在每个文件的头部。

**坑4: 给博客加评论**  
网上教程列出来的评论要么被墙了（如disqus），要么要备案（如搜狐畅言）。折腾了好久，终于找了一个，目前能用的，叫[来必力](https://livere.com/)。使用过程需要修改模版中关于评论板块的内容。  
另外，每篇文章可以单独定义是否需要加载评论区，在头部定义参数`comments: true`即可

如果想深度定制模版，可以参考[jekyll官方文档](https://jekyllrb.com/docs/home/)。其他内容欢迎讨论。