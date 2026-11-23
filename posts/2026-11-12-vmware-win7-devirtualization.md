---
title: Win7 虚拟机去虚拟化教程：VMware 16.1.2＋HardenedLoader 驱动（mini-PC／ThinkPad 双机版）
date: 2026-11-12
tag: VMware 工具
tagkey: vmware
slug: vmware-win7-devirtualization
excerpt: VMware Workstation 16.1.2 上 Win7 虚拟机的去虚拟化教程：改 .vmx、改 vmware-vmx.exe（显卡 PCI ID＋v2 代码补丁）、VMwareCloak 注册表清理、HardenedLoader 驱动；mini-PC 通用版与 ThinkPad 版两个包，绝不能混用。先说实话：VMP 3.4／3.50 目前仍未通过，驱动也未在 Win7 上实测加载。
---

## 先说结论

这篇教程是 2026-11-12 在两台机器上实测过的去虚拟化做法：mini-PC 白牌小主机（Celeron N5105）和 ThinkPad X1 Carbon 2017（i7-7600U），宿主都是 Windows 10，VMware Workstation 16.1.2，客机 Win7 x64。

- **显卡那一项已解决**：v2 代码补丁生效后，mini-PC 的 Win7 客户机里显卡不再是 VMware SVGA，wmic 显示标准 VGA 图形适配器，硬件 ID 为 Intel UHD Graphics（DEV_4E61）。
- **但 VMP 3.4／3.50 目前仍未通过**：mini-PC 通用版实测，VMP 3.4 检出、VMP 3.50 检出、Pafish 检出，只有 VMP_SE 通过。没有任何公开方案被验证过能绕过 VMP 3.4／3.50，本教程也不保证。
- **驱动未实测加载**：HardenedLoader 驱动已在 mini-PC 上编译通过（MSBuild 0 错误 0 警告），但从未在 Win7 上实测加载；Win7 SP1 的 ntoskrnl 里驱动要找的特征是否存在未知，装完必须用 DbgView 核对日志。
- **虚拟机已恢复原版配置**：去虚拟化深挖停下后，mini-PC 的 Win7 虚拟机已换回原版 .vmx 与原版 vmware-vmx.exe，能正常开机。Tools 服务仍是停的（原版配置下也起不来，是去虚拟化之前就有的老毛病，正在干净重装）。

## 准备工作

- **先做快照，再动手**。换 .vmx 或 vmware-vmx.exe 之前，先在 VMware 里给 Win7 虚拟机做一个新快照，出问题靠快照回退。教训：mini-PC 那台的快照链曾因磁盘被多方共用出问题，导致快照还原失败（报虚拟磁盘被使用过多次），所以换之前务必另做新快照。
- **两个包绝不能混用**。mini-PC 通用版与 ThinkPad 版的 .vmx、vmware-vmx.exe 都是按各自宿主硬件改的，值完全不同，混用必错。
- **驱动不在去虚拟化包里**，是另外单独编译、单独发送的（见下文“驱动”一节）。
- **不要在虚拟机运行时换 .vmx 或 vmware-vmx.exe**。换之前确认虚拟机已关机、VMware Workstation 已退出。

## 包内容

### mini-PC 通用版 v2

文件 `win7-devirtualization-minipc-generic-v2.zip`，7,453,434 字节，MD5 `db616e6c…`，SHA256 `dacc7df8…`。包内：

- `Windows 7.vmx`：改后 .vmx（通用版，151 行，原版 121 行）
- `Windows 7-原版备份.vmx`：原版 .vmx 备份，出问题直接换回去
- `vmware-vmx.exe`：改后 VMware 主进程（16.1.2，v2 代码补丁版，18,835,712 字节，MD5 `41c31d87…`）
- `VMwareCloak.ps1`：VMwareCloak v0.4（开源脚本，与 ThinkPad 版同一份）
- `README.md`：本包的分步操作与回退方法
- `vmware-vmx-通用改版说明.md`：vmware-vmx.exe 改版细节（版本、MD5、改动点）

### ThinkPad 版 v2

文件 `win7-devirtualization-thinkpad-v2.zip`，7,463,609 字节，MD5 `9c4e0ee3…`，SHA256 `0bdc4dcc…`。包内：

- `Windows 7.vmx`：V4 .vmx（168 行，已加固）
- `vmware-vmx.exe`：显卡 PCI ID 改版（18,835,712 字节，MD5 `5eb40de5…`）
- `VMwareCloak.ps1`：与 mini-PC 版同一份
- `vmware-vmx-显卡改版说明.md`：显卡改版的改动点、定位依据、验证结果
- `调研报告-最好办法.md`：14 项检测点、各方案对比、推荐路径、来源链接
- `README.md`：分步操作顺序与回退方法

### 驱动（HardenedLoader，已编译好）

驱动是 Win7 x64 通用内核驱动，不绑机器硬件，mini-PC 与 ThinkPad 的 Win7 虚拟机都能用（但两个包里的 .vmx／vmware-vmx.exe 绝不能混用）：

- `vmloader-signed.sys`：617,848 字节，SHA256 `ea33406c…`（测试签名，无时间戳）
- `vmloader-signed.zip`：118,162 字节，SHA256 `21a00e76…`（仅含 .sys）
- `VmLoaderTest.cer`：772 字节，SHA256 `eec3c046…`（自签测试证书，CN=VmLoader Test，有效期至 2031-11-12）
- `INSTALL.md`：客机安装／验证／卸载／回退手册
- `README.md`：方案、覆盖点、风险（注意：该文件头部“仅手册，未编译出包”是编译前的旧状态，已过时；驱动已于 2026-11-12 编译通过）

驱动源码是 VmwareHardenedLoader 旧版（commit fdf42504，2022-12-02，MIT 协议），现行 ng 版已不支持 Win7。编译工具链为 VS2019 Build Tools＋WDK／SDK 10.0.19041；源码打了两处 Win7 补丁（`NonPagedPoolNx` 改 `NonPagedPool`、加一条 warning 屏蔽）。

## 两台机器的区别

- **宿主**：mini-PC 白牌小主机（Celeron N5105，UHD Graphics，SMBIOS 全是 "Default string"）；ThinkPad X1 Carbon 2017（i7-7600U，Intel HD 620，SMBIOS 为 LENOVO／20HRCTO1WW）。
- **CPU 品牌串**：mini-PC 原版 .vmx 本来就没有 cpuid 行，VMware 默认透传宿主真实 N5105 品牌串，不用再写；ThinkPad 版的 cpuid 行是修正原来写错的假品牌串。
- **SMBIOS**：两版都开 `SMBIOS.reflectHost`，但 mini-PC 反映宿主后显示 "Default string"（白牌宿主的真实值，无 VMware 字串，但占位符本身显得假；改 SMBIOS 字串要改 BIOS，会破校验和黑屏，不能走）。
- **网卡 MAC**：两版都把 .vmx 网卡改成静态 MAC，用宿主真实网卡的 OUI 前缀加虚拟机 UUID 后缀，不用 VMware 的 00:0C:29 前缀；具体值按各自宿主硬件填，两包绝不能混用。
- **硬盘**：mini-PC 版 .vmx 写 TEAM／TM8FP6256G；ThinkPad 版写 SAMSUNG／MZVLW1T0（各自宿主硬盘的真实厂商与型号）。
- **显卡 PCI ID**：mini-PC 版改成 Intel UHD Graphics（DEV_4E61）；ThinkPad 版改成 Intel HD Graphics 620（DEV_5916）。
- **vmware-vmx.exe 设备名**：mini-PC 版 17 处 `VMware Virtual` 改 `Common Virtual`（白牌无品牌可写，写 Lenovo 是假冒）；ThinkPad 版 15 处改 `Lenovo Virtual`。
- **vmware-vmx.exe 原版 MD5 不同**：同为 16.1.2、同为 18,835,712 字节，但 mini-PC 原版 MD5 `488a4bbb…`、ThinkPad 原版 MD5 `3149e1bf…`，是不同小构建，改版时以各机本机文件为准。

## 安装步骤

### 第 0 步：做快照（必做）

在 VMware 里给 Win7 虚拟机做一个快照再动手，后面任何一步出问题都靠快照回退。

### 第 1 步：换 vmware-vmx.exe

1. 关虚拟机，退出 VMware Workstation，确认无 vmware-vmx.exe 进程在跑。
2. 备份安装目录 `x64` 下的原版 `vmware-vmx.exe`（先核对 MD5 与上文一致）。
3. 把本包的 `vmware-vmx.exe` 拷过去覆盖。
4. 重启 VMware，开机进 Win7，设备管理器里核对显卡硬件 ID 是否已变（mini-PC 应为 Intel UHD Graphics DEV_4E61；ThinkPad 应为 Intel HD 620 DEV_5916）。

回退：用备份的原版覆盖回去即可。

### 第 2 步：换 .vmx

1. 确认 Win7 虚拟机已关机（不要在运行中换 .vmx）。
2. 备份虚拟机目录下的原版 `Windows 7.vmx`（原版已在包内）。
3. 把本包的 `Windows 7.vmx` 拷到虚拟机目录覆盖。

回退：换回原版 .vmx，或恢复第 0 步的快照。

### 第 3 步：跑 VMwareCloak（注册表）

只在虚拟机内部做，只对客机 Win7 生效，不动宿主。把包内的 `VMwareCloak.ps1` 拷进虚拟机，以 SYSTEM 权限跑注册表模式（`-reg`），清理注册表里的 VMware 相关键（SCSI 标识、显示驱动描述、BIOS 厂商／版本、系统制造商／产品名等）。具体做法见包内 README。

说明：只跑 `-reg` 即可。`-all` 是 `-reg`＋`-procs`＋`-files` 三项全开，但没装 VMware Tools 的机器上，要杀的 Tools 进程与要改名的 VMware 文件根本不存在，相对 `-reg` 基本没有额外收益。注意 VMwareCloak 的 `-reg` 只改注册表里的描述串和 SCSI 标识，没有改 PCI 枚举键下 VMware 的设备键，这一项它盖不住。

回退：恢复第 0 步的快照。

### 第 4 步：HardenedLoader 驱动

按驱动包内 `INSTALL.md` 操作，全程在 Win7 虚拟机里，先做快照：

1. **前置核对**：.vmx 加固项、硬盘厂商／型号、MAC 号段、显卡 PCI ID、VMwareCloak `-reg` 已跑过、虚拟机内**没有装 VMware Tools**（上游明确警告：装 Tools 会毁掉一切）、已做快照。
2. **装测试证书**：把 `VmLoaderTest.cer` 拷进虚拟机，双击安装到“受信任的根证书颁发机构”，再装一次到“受信任的发布者”；装完后看 `vmloader.sys` 属性里的数字签名页，应显示签名者正常。
3. **开测试签名模式**：管理员 cmd 里开测试签名，重启虚拟机；重启后桌面右下角出现 Test Mode 水印是正常的。提醒：测试模式本身可被检测，这是用这个驱动必须付的代价。
4. **安装驱动**：把 `vmloader.sys` 和 `install-vmloader.bat` 拷进虚拟机同一文件夹，右键安装脚本以管理员身份运行（预检→拷驱动到系统盘→创建系统启动型服务→启动服务→清理一条 VMware 的 ACPI 注册表项→提示重启）。
5. **验证**：服务状态应为运行中；再用 DbgView（选 Capture Kernel）看驱动启动日志，三条“node manipulated!”全有才算三个固件表过滤已就位；若出现特征未找到之类的错误，驱动在该内核版本上无效，不要反复重装。
6. **跑检测工具**：按之前的方法逐项跑 VMProtect 3.4／3.50 等，记录每一项的变化。

卸载：右键卸载脚本以管理员身份运行（停服务→删服务→删驱动文件→提示重启）；或关测试签名去水印；最彻底是恢复第 0 步的快照。

### 第 5 步：验证

开机进 Win7，按顺序跑检测工具，记录每一项的变化：VMProtect 3.4／3.50、Pafish、chkVM、VM_XNJ、VMP_SE 等。哪项过了、哪项还报，是下一步决策的依据。

## .vmx 改了什么（mini-PC 通用版）

改后 .vmx 共 151 行（原版 121 行＋30 行新增），要点：

- `hypervisor.cpuid.v0`／`v1` 置 FALSE，隐藏 hypervisor 位
- `monitor_control.restrict_backdoor` 置 TRUE，禁后门端口
- `monitor_control.virtual_rdtsc` 置 FALSE，关虚拟 RDTSC
- `monitor_control.disable_directexec`／`disable_btseg` 等加固项置 TRUE
- `isolation.tools.*.disable` 五项置 TRUE，禁 Tools 通道
- `SMBIOS.reflectHost` 及相关三项置 TRUE，SMBIOS 取宿主真实值；`SMBIOS.noOEMStrings` 置 TRUE，去 OEM 字串
- `scsi0:0.vendorID`／`productID` 写宿主硬盘真实厂商与型号
- 网卡改静态 MAC（宿主网卡 OUI 前缀＋虚拟机 UUID 后缀），`ethernet0.checkMACAddress` 置 FALSE
- 没有加 cpuid 品牌串行（mini-PC 原版 .vmx 本来就没有，VMware 默认透传真实 N5105 品牌串）

## vmware-vmx.exe 改了什么

### v1：字符串与 PCI ID（两版通用做法）

- 设备名改串（等长替换，文件大小不变）：mini-PC 版 17 处 `VMware Virtual` 改 `Common Virtual`；ThinkPad 版 15 处改 `Lenovo Virtual`（设备名后缀不变，只换前缀）。
- 显卡 PCI ID 两处（文件偏移 0x011DA62C 与 0x011DB76A，原字节 `05 04 ad 15`）：mini-PC 版改 `61 4E 86 80`（Intel UHD Graphics DEV_4E61）；ThinkPad 版改 `16 59 86 80`（Intel HD Graphics 620 DEV_5916）。

### v2：代码补丁（mini-PC 版，2026-11-12）

v1 的字符串补丁对客户机可见显卡 ID 不生效：换上 v1 后客户机里仍是 VMware SVGA 3D（DEV_0405）。v2 在 v1 基础上再加 4 处代码补丁（SVGA PCI 配置空间设置函数，文件偏移约 0x221560 起）：厂商 `15AD` 改 `8086`，设备 `0406`／`0711`／`0405` 改 `4E61`。v2 与 v1 仅差 8 字节，与原版差 118 字节。

实测（2026-11-12，mini-PC Win7 客户机）：wmic 显示“标准 VGA 图形适配器”，硬件 ID 为 Intel UHD Graphics（DEV_4E61），VMware SVGA 驱动不再绑定（回落标准 VGA，VNC 仍可用）。但 VMP 3.4／3.50 在 v2 下仍检出——显卡只是众多检测向量之一。

## 实测结果（2026-11-12，mini-PC）

- **VMP 3.4 检出、VMP 3.50 检出**；Pafish 检出（VMware 注册表键、vmmouse.sys、vmhgfs.sys、vmci 相关项；CPU RDTSC 计时两次运行其一）；Tencent 2016 检出 3／8；**VMP_SE 唯一通过**；chkVM 挂死约 2 分钟无结论。
- **显卡 v2 代码补丁生效**（见上节），但 VMP 3.4／3.50 仍检出。
- **Tools 服务是去虚拟化之前就有的老毛病**：原版 .vmx＋原版 exe 下服务仍是停止状态，重装也没修好，与去虚拟化改动无关；正在做干净卸载＋重装。
- **虚拟机已恢复原版配置并能开机**：.vmx 与 vmware-vmx.exe 均已换回原版（MD5 已核对），客户机内检测工具痕迹已清干净。
- **驱动未实测加载**：Win7 SP1 的 ntoskrnl 里驱动要找的特征是否存在未知；若 DbgView 出现特征未找到，驱动在此内核版本上无效，此路不通。
- **残留向量**：FIRM 表与 RDTSC 时序是 VMP 仍失败的最可能原因；FIRM 表只有运行时过滤（驱动）或换 hypervisor 才能盖，RDTSC 时序在 VMware 上没有公开的根治办法。

## 禁区（已实证，不要碰）

- **BIOS 一律用原版，不要改串**。改串会破校验和，虚拟机黑屏起不来（2026-11-12 实证）。ThinkPad 包内 README 里曾有 Phoenix BIOS Editor 改 BIOS 一步，已按实测纠正：不要做。
- **.vmx 不要加 `bios440.filename` 行**。它是相对路径，VMware 只到虚拟机目录找 BIOS，加了反而找不到（2026-11-12 实证）。
- **不要把 ThinkPad 的硬件值写进 mini-PC 的版本**（反之亦然）。i7-7600U、20HRCTO1WW、MZVLW1T0、HD 620、5916、Lenovo 与 N5105、TEAM、TM8FP6256G、4E61、Common Virtual 各归各的包。
- **不要跑 VMwareCloak 的 `-reg` 以外模式凑数**，也不要改 BIOS、不要动 ThinkPad 之外的机器。
- **驱动不保证过 VMP 3.4／3.50**（上游只验证过 3.2）；新一代检测器已专门收录该驱动的补丁手法，驱动本身也可能成为新指纹；测试签名水印本身可被检测；内核驱动有蓝屏风险，操作前必须做快照。

## 下载

去虚拟化包（mini-PC 通用版 v2、ThinkPad 版 v2）与驱动（vmloader-signed.zip、VmLoaderTest.cer）目前走聊天记录里的临时下载链接，链接会过期，需要时取最新链接。**本帖不贴临时链，也不编永久链**，等固定下来再更新。
