---
title: 软件图书馆同步：大金 2.2.46（修 panic 反复重启：状态灯任务栈溢出）
date: 2026-11-08
tag: 大金固件
tagkey: daikin
slug: software-sync-2026-11-08
excerpt: 大金 2.2.46：修夜间模式下 panic 导致的反复重启（启动次数 2266），根因是状态灯闪烁任务栈仅 1024 字节、nightActive() 调 time() 调用链过深致栈溢出；2.2.45 的室外空气 AQI 修复保留；已核对 Release 与哈希。
---

## 这次同步了什么

只同步最新版。大金 2.2.46：

- **大金传感器固件 2.2.46**：修复 panic 导致的反复重启（启动次数 2266，rst=4）。根因：HomeSpan 状态灯闪烁任务栈仅 1024 字节，nightActive() 里调 time() 的调用链太深致栈溢出、空指针 panic，夜间模式开启时触发。修法：主循环每分钟算一次夜间状态存标志，nightActive() 只读标志，不再调 time()。2.2.45 的室外空气修复（AQI）原样保留。
- 文件 firmware-slim-2246.bin，1,947,296 字节，SHA256 `c4c684da7c1bb7d44080c54031e9cc1f07fe8458bda0428e93eb364626384bf4`。私有仓 Release，需 GitHub 登录态下载。已验证：Release 已发布（非草稿）、资产 state=uploaded，大小与 SHA256 与本地构建产物逐字节一致。本版 1,947,296 字节，OTA 槽为 1,966,080 字节，网页 OTA 可直接升级；2026-11-07 23:28 已由网页后台 OTA 成功上机，11-08 09:12 复查连续运行 9 小时 39 分零重启，panic 已修好。

永久链：[firmware-slim-2246.bin](https://github.com/aliporcins/daikin-firmware/releases/download/v2.2.46/firmware-slim-2246.bin)（GitHub Release，私有仓，需 GitHub 登录态下载）。

## 故意没进馆的

- 大金销售版固件：含激活门控的闲鱼销售线，绝不公开分发，不进馆、不进博客。
- 大金 2.2.38–2.2.45 中间构建：只有本地构建文件、无正式 Release，不进馆；现已被 2.2.46 取代，不要再刷。
- NOVX 1.0.9x-test 草稿：测试版直链永不进博客或图书馆。
