---
title: WeTalk/PingMe 自动签到上 Cloudflare：weping 部署小记
date: 2026-11-08
tag: 接单学习
tagkey: plan
slug: weping-checkin
excerpt: GitHub 版签到一直 +0，因为接口只认手机端请求。换成 weping：直接重放手机上抓到的真实请求，签到和视频奖励都能拿；跑在 Cloudflare Workers＋D1 上，每天 05:20 自动跑一次，地址是 weping.hench.cc.cd。
---

## 为什么换 weping

WeTalk 和 PingMe 的 GitHub 版签到一直 +0：余额能读，但签到和视频奖励拿不到。根因是这两个接口只认手机端请求，GitHub Actions 发过去的请求直接被软拒。

weping（Yu9191 的开源项目）换了个思路：不从头拼请求，直接重放手机上真实抓到的请求参数和请求头。手机上能签到的请求，原样重放就能签到。

## 部署

- Worker：`weping`，地址 https://weping.hench.cc.cd/（已绑自己的域名，不再用 workers.dev 的地址）
- 存储：Cloudflare D1，账号数据、日志、会话都存在里面
- 定时：Cron `20 21 * * *`，每天 05:20 自动跑一次签到＋视频奖励
- 管理后台：Worker 自带网页后台，能看余额、手动执行、开关账号

部署时遇到两个小插曲：

- D1 满了。账号里 D1 数据库已满 10 个，建不了新的；其中 `notes-db` 是幽灵条目（列表里有，实际不存在，也删不掉，占着一个名额）。先把 weping 的表建在现有的 `clash-sub` 库里，表名不冲突，不影响原来的库。以后在控制台把幽灵库清掉腾出名额后，再迁到独立库。
- 定时触发器直接调 API 一直报解析错误，改走 wrangler 部署才把 Cron 加上。

## 怎么用

1. 打开 https://weping.hench.cc.cd/，用管理密码登录后台
2. 后台里取 Loon 模块链接，装到手机 Loon 上
3. 打开 PingMe、WeTalk App 各一次，模块会拦截一次余额查询请求，把账号数据传给 Worker
4. 之后每天 05:20 自动签，不用再管；余额和日志都在后台能看到

## 和 GitHub 版的关系

GitHub 那边的 PingMe/WeTalk 任务继续保持暂停，weping 是独立的一套，不冲突。等 weping 跑稳了，GitHub 那边就不用再惦记这两站了。
