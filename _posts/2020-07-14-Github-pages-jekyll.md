---
layout: post
title: "使用jekyll搭建Github pages个人博客（含本地调试方法）"
date: 2020-07-14 11:14:00
description: jekyll, github, github pages
share: true
comments: true
tags:
 - 学习笔记
 - jekyll
---



本地调试
由于jekyll将地址绑定到了127.0.0.1，导致局域网的其它机器并不能访问它的服务。但实际上只要改变运行jekyll的参数就可以了。
$ jekyll serve -w --host=0.0.0.0
 
Server address: http://0.0.0.0:4000/
 
Server running... press ctrl-c to stop.


ref: http://qiubaiying.vip/2017/02/06/%E5%BF%AB%E9%80%9F%E6%90%AD%E5%BB%BA%E4%B8%AA%E4%BA%BA%E5%8D%9A%E5%AE%A2/

https://jekyllrb.com/

