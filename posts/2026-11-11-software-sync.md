---
title: 软件图书馆同步：NOVX Pro 1.0.3 正式版（1.0.113 测试树出正式安装包）
date: 2026-11-11
tag: NovaPlayer
tagkey: novaplayer
slug: software-sync-2026-11-11
excerpt: NOVX Pro 正式版 1.0.3：以 1.0.113 测试树出正式安装包（带版本信息与图标），含 1.0.51–1.0.113 全部测试批累计改动；本版直接改动为 F11 全屏圆角区域残留修复（koffi 原生清区域，VM 实测 via=native）；已核对 Release 与哈希，VM 静默安装与卸载冒烟通过。
---

## 这次同步了什么

只同步最新版。NOVX Pro 正式版 1.0.3（上一正式版为 1.0.2）：

- **NOVX Pro 1.0.3**：以 1.0.113 测试树出的正式安装包，带版本信息与图标；含 1.0.51–1.0.113 全部测试批自 1.0.2 以来的累计改动。
- **本版的直接改动是 F11 全屏圆角区域残留修复**：F11 后窗口 RECT 已是全屏、内容也已重排，真正残留的只有旧圆角区域仍在裁剪（右缘与下缘透出后方窗口／任务栏）；修法是 koffi 直调 user32 SetWindowRgn(NULL) 原生清区域（PowerShell 回退），VM 实测 main-window.log 里 via=native、4 行全 ok=1，F11 进／退 × 窗口化／最大化均通过；真实文件播放、STRM 回填＋去重、NSIS 安装冒烟亦通过。
- 文件 NOVX.Pro.Setup.1.0.3.exe，203,874,846 字节，SHA256 `7d80b064d004b070119ae1d7d7a0bd5e719c068128540d1bc41405c53b73cb1e`。私有仓 Release，需 GitHub 登录态下载。已验证：Release 已发布（非草稿）、资产 state=uploaded，大小与 SHA256 与 CI 构建产物逐字节一致，asar 内版本串为 1.0.3，源码与 1.0.113 测试树逐字节一致（仅 Windows 换行符差异）；VM 静默安装（/S，退出码 0）与系统自带卸载器卸载均通过，用户数据完整保留。安装包由仓库 CI 构建，tag 指向本次构建提交。

永久链：[NOVX.Pro.Setup.1.0.3.exe](https://github.com/aliporcins/nova-player/releases/download/v1.0.3/NOVX.Pro.Setup.1.0.3.exe)（GitHub Release，私有仓，需 GitHub 登录态下载）。

说明一点：2dland 预览＋删除同步在 VM 上未验证（VM 上 0 条任务，属覆盖缺口，非阻断）；首启 explorer 重启在 VM 上两次均未出现（1.0.113 与 1.0.3 冒烟），根因未定位，不称已修复。

## 故意没进馆的

- 大金销售版固件：含激活门控的闲鱼销售线，绝不公开分发，不进馆、不进博客。
- NOVX 1.0.113-test 解压包与 1.0.114、1.0.115-test 草稿：测试版直链永不进博客或图书馆。
- 1.0.2 正式版条目保持原样不动，留作历史；1.0.3 在此基础上接续。
