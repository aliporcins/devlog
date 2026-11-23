---
title: 软件图书馆同步：大金 2.2.37（TVOC 提醒防抖：回滞＋5 分钟回落确认）
date: 2026-11-07
tag: 大金固件
tagkey: daikin
slug: software-sync-2026-11-07
excerpt: 大金 2.2.37：TVOC 提醒加回滞（须低于阈值 80% 才算回落）与 5 分钟回落确认，治反复超标/回落刷屏；通知通道改走 Bark；已实机 OTA 验证，设备已跑 2237。
---

## 这次同步了什么

只同步最新版。大金 2.2.37（版本号升一位，不再是 r 系同版本串换文件）：

- **大金传感器固件 2.2.37**：TVOC 提醒防抖两项——回落判定加回滞，须低于阈值的 80% 才算回落（如 TVOC 阈值 600，须到 480 以下）；回落确认由连续 2 次采样（约 20 秒）延长到连续 30 次（约 5 分钟）。此前 TVOC 在阈值上下波动时会反复超标/回落刷屏。超标判定本身未动（仍是数值大于阈值即超标），五项提醒的阈值与开关未动。r33 自检全部保留：启动记录、WiFi 久连不上自动升级、上电传感器点名。
- 文件 firmware-slim-2237.bin，1,834,576 字节，SHA256 `e3f3ad9d4efe99c6910f78433c9b3b3a90fd616f5cffdf0f98d78a313b107ab0`。私有仓 Release，需 GitHub 登录态下载。已实机 OTA 验证：设备后台 /update 上传一次成功，重启后在线、版本显示 2237，传感器读数正常，设置与通知配置未动。

- **通知通道改走 Bark**：此前经微信推送，现改走 Bark 直推 iPhone（Worker 侧改动，不在固件内）：daikin-notify Worker 加 Bark 分支，自定义域名 daikin-notify.hench.cc.cd，传感器 Worker 地址已改到新域名并端到端验证通过。点通知不再自动跳转，后台地址附在正文末尾，需要时再点。

永久链：[firmware-slim-2237.bin](https://github.com/aliporcins/daikin-firmware/releases/download/v2.2.37/firmware-slim-2237.bin)（GitHub Release，私有仓，需 GitHub 登录态下载）。

## 故意没进馆的

- 大金销售版固件：含激活门控的闲鱼销售线，绝不公开分发，不进馆、不进博客。
- 大金 2.2.36 r32：窄屏免打扰时间框改版的临时文件，正式永久链仍是 r10，未动；现已被 2.2.37 取代，不要再刷。
