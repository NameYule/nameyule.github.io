---
layout: post
title: "使用jekyll搭建Github pages个人博客（含本地调试方法）"
date: 2020-07-14 11:14:00 +0800
keywords: jekyll, github, github pages
description: jekyll, github, github pages
tags: [学习笔记]
---


本地调试
由于jekyll将地址绑定到了127.0.0.1，导致局域网的其它机器并不能访问它的服务。但实际上只要改变运行jekyll的参数就可以了。
$ jekyll serve -w --host=0.0.0.0
 
Server address: http://0.0.0.0:4000/
 
Server running... press ctrl-c to stop.


ref: http://qiubaiying.vip/2017/02/06/%E5%BF%AB%E9%80%9F%E6%90%AD%E5%BB%BA%E4%B8%AA%E4%BA%BA%E5%8D%9A%E5%AE%A2/

https://jekyllrb.com/




**坑1: 模版选择**  
最初看的[教程](https://github.com/litaotao/litaotao.github.io)里面只告诉我直接克隆里面的模版使用，我以为只有一种方式可以选，后来尝试过程中才发现模版本身可以自己定制（[从0开始定制方法看这里](http://www.ruanyifeng.com/blog/2012/08/blogging_with_jekyll.html)），当然网上也有大量现成的可以用，从[这里](https://github.com/jekyll/jekyll/wiki/Themes)挑选。

**坑2: github仓库命名**  
git开通github page的时候，要求建一个仓库，仓库命名有讲究。我开始用github.io命名，也能打开页面，但是就变成https://nameyule.github.io/github.io这样了，不能通过https://nameyule.github.io直接访问。后来才发现，命名必须是“nameyule.github.io”这样（不带引号）。

**坑3: 文章标签**  
文章标签是脚本自动添加的，但是在模版里面，要在头部（官方叫[front matter](https://jekyllrb.com/docs/frontmatter/))定义tag标签，定义的形式类似这样：
```Ruby
---
tag: 笔记 
---
```
注意这段内容不能挪位置，必须放在每个文件的头部。

**坑4: 给博客加评论**  
网上教程列出来的评论要么被墙了（如disqus），要么要备案（如搜狐畅言）。折腾了好久，终于找了一个，目前能用的，叫[来必力](https://livere.com/)。使用过程需要修改模版中关于评论板块的内容。  
另外，每篇文章可以单独定义是否需要加载评论区，在头部定义参数`comments: true`即可。
  
如果想深度定制模版，可以参考[jekyll官方文档](https://jekyllrb.com/docs/home/)。其他内容（如底部的链接定制）欢迎讨论。
