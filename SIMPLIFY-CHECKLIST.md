# 整站精简清单（2026-11-17，用户标准：精简易懂）

标准：删一切不帮读者理解的废话；段落要短，一句话能说清的不用两句；术语首次出现即解释；结构一眼能扫完。数字、大小、SHA、地址、步骤一律原样保留，只动措辞。

## 完成记录（2026-11-17）

29 篇全部改完（AX6000 除外）。build.py 模板文案已改（见上节）。构建 EXIT 0（30 篇），生成页无 `| ---` 残留，AX6000 页含 `<figure class="md-video">` 且 iframe src 为 `https://www.youtube.com/embed/gg4KD8qLGSI?start=428`。部署 EXIT 0，URL：https://9126be1e.devlog-6v1.pages.dev（66 文件，17 已上传）。

后 20 篇改后行数（现查）：novx-v1216-milestone 36、novx-pro-1.0.1 33、side-router-warp-daed 67、warp-bypass-router 46、daily-checkin-sites 106→101、weping-checkin 37、yu9191-tools 119→117、home-network-offline-guide 188→184、novx-devlog 48、vmware-win7 167、daikin-2247 23→26、daikin-2248 23→26、daikin-2249 23→25、software-sync 10-29 27→29、10-30 30→33、11-04 19→20、11-07 23→24、11-08 22→23、11-10 24→26、11-11 24→26。模板帖行数略增是巨型 bullet 拆成短条所致（每段更短、更好扫），不是没精简。

事实更新（改时一并修正）：weping 定时全站改成每天 05:20（Cron `20 21 * * *`）；daily-checkin-sites 里雨晨改为已暂停（2026-11-17 起站方证书问题）、MuseBoostBot 改为已停（2026-11-14 起不再签）、GitHub 三站改两站（V2EX／福利吧）。

## 现状与改法

### build.py（模板与入口文案）
- 现状：首页 Hub 12 入口卡＋3 家里服务卡，卡片描述多为两句；导航 6 项（首页／我的游戏／开发记录／学习计划／日志／软件图书馆）；页脚两句；日志页 hero 两句；游戏／记录／服务清单／计划总览的 hero 各 1–2 句长段；大金刷机指南（build_guide）多处长句。
- 改法：导航标签已是人话，不动标签；页脚缩成一句；首页 hero、家里服务提示、底部导航提示各缩成一句；12 张入口卡描述各砍到一句话；游戏 4 张卡、记录 5 张卡描述各砍到一句；日志／游戏／记录／服务清单 hero 各缩成一句；计划总览两段长 hero 并成一段短的；服务清单首尾说明各缩一句；刷机指南只做措辞精简（步骤、数字、SHA、命令、禁忌一字不动）。

### 文章列表（log.html）
- 现状：卡片摘要取自各文章 front matter 的 excerpt，多篇 excerpt 是 2–3 句长串。
- 改法：每篇 excerpt 砍到 1–2 个短分句（随各文章正文一起改）。

### 文章（29 篇，AX6000 那篇不动）
| 文章 | 现状 | 改法 |
|---|---|---|
| daikin-th-calibration（38行） | 开篇、系数、对表三段偏长；尾巴一段跑题感 | 每段砍三分之一；尾巴缩成两句 |
| np-libmpv-journey（37行） | 起点、真机、分诊三段偏长 | 每段砍三分之一；定版一段不动 |
| daikin-pairing-port80（51行） | 排查长征 6 条偏长；终局、修复段偏长 | 每条砍到一句；教训句保留 |
| gig-learning-plan-28days（32行） | 开篇两段、课表 5 条、每天怎么用、方法论都长 | 开篇并成一段；每条砍一半；方法论缩成两句 |
| np-112-sound-no-picture（37行） | 翻车两条、定罪一段、热修 8 条偏长 | 每条砍到一句；结论句保留 |
| np-1122-diagnostics（42行） | 反馈、engine、winbounds、开方、教训都长 | 每段砍三分之一；教训句保留 |
| toolbox-libimobiledevice（36行） | 现象、定责、决定三段偏长 | 每段砍三分之一；总结句保留 |
| poke-pve-1-1-1（30行） | 已较短；excerpt 是长串 | excerpt 砍一半；正文微调 |
| novx-v1216-milestone（36行） | 五节各有冗余句 | 每节砍 1–2 句；惯例说明保留 |
| novx-pro-1.0.1（33行） | 开篇、含什么 6 条偏长 | 每条砍到一句；核对节保留 |
| daikin-2236-r32（22行） | 已短；excerpt 长串 | excerpt 砍一半；正文微调 |
| side-router-warp-daed（67行） | 每节都有冗余句；拓扑 4 条可并 | 每节砍三分之一；拓扑 4 条并成 2 条 |
| warp-bypass-router（46行） | 每节偏长 | 每节砍三分之一；现态保留事实 |
| daily-checkin-sites（106行） | **含 2 张表格（渲染器不支持）**；每站 5 小项重复啰嗦；excerpt 过时（weping 每 3 小时已改为每天 05:20） | 两张表改短列表；每站砍掉重复项、步骤只留要点；weping 处改成每天 05:20；通用处理并成一段 |
| weping-checkin（37行） | excerpt 与正文多处“每 3 小时”已过时（现为每天 05:20） | cron 相关三处改成每天 05:20；其余措辞微调 |
| yu9191-tools（119行） | **含 1 张一览表**；5 个工具节各有长句 | 一览表改短列表；每节砍三分之一；“没碰的东西”保留 |
| home-network-offline-guide（188行） | **含 2 张表格**；手册体，步骤不可少但措辞可压 | 两张表改短列表；每段砍三分之一；步骤、地址、数字、红线一字不动 |
| novx-devlog-2026-11-10（48行） | 1.0.110 一条数字墙；各节有冗余句 | 数字原样保留、措辞压短；“没进博客”节缩成一句 |
| vmware-win7-devirtualization（167行） | 结论 4 条、包内容、两机区别 8 条、安装 6 步、改动清单、实测、禁区都长 | 每条砍三分之一；文件、数字、SHA、命令、禁区一字不动 |
| daikin-2247／2248／2249（各23行） | 模板化三篇；excerpt 是长串；正文是一段巨型 bullet | excerpt 砍到一句；巨型 bullet 拆成 3 条短的；指南同步句缩短 |
| software-sync 10-29／10-30／11-04／11-07／11-08／11-10／11-11（7篇） | 模板化；excerpt 长串；正文巨型 bullet；“故意没进馆”重复 | excerpt 砍到一句；巨型 bullet 拆成短条；重复句压短；数字与链接不动 |

### 不动的
- AX6000 文章正文结构（只做渲染确认）；build.py 的 `!video` 语法与 `.md-video`/`.video-wrap` 样式；渲染器核心逻辑；部署配置与域名；decode/notepad/weping 三个工具页（功能页，非文章）；plan_data.py 的 28 天逐日内容（已是清单体）；静态资源与图片。

## 验法
- 构建 EXIT 0；生成页无 `| ---` 残留；AX6000 页含 `<figure class="md-video">` 且 iframe src 正确；部署 URL 能打开；每篇行数／excerpt 现查核对。
