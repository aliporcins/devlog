# 开发日志博客（devlog）

线上：https://devlog-6v1.pages.dev （Pages 项目名 devlog 已被占用，平台分配 devlog-6v1）

黑曜金静态站，全站导航四分区：

**视觉定版（2026-10-24）**：背景为 B「深空竖渐变」（自上而下 `#0b0f16 → #05070a`），点缀包五样全开（标题渐变金短线 + 区块标题小菱形、卡片金色渐变描边与微光、细金线 + 中央菱形分隔 `.orn`、极淡 46px 细网格纹理、徽章/标签/筛选与主按钮同色系微渐变）。参数原样移植自预览页 `site/preview-bg.html` 的 theme-b 与 deco-on 实现（预览页保留作存档）。

| 分区 | 文件 | 内容 |
|---|---|---|
| 首页 | `site/index.html` | 产品家族一览 + 最新 4 篇文章 |
| 我的游戏 | `site/games.html` | 游戏卡片（状态徽章：已发布/样板/开发中/筹备中） |
| 开发记录 | `site/records.html` | 各产品版本时间轴入口（NovaPlayer / 筋斗小圣 / IPA 工具箱版本页 + 博客内标签流） |
| 学习计划 | `site/plan.html` + `site/plan/day-N.html` | 28 天接单学习计划：总览按周分组，逐日一页（目标/学什么/要点速记/练习/打卡）。逐日内容在 `plan_data.py` 的 `PLAN_WEEKS`，改内容改数据文件后重跑 build |
| 日志 | `site/log.html` | 全部博文流，支持按产品标签筛选（`?tag=novaplayer|daikin|toolbox` 深链） |
| 文章页 | `site/posts/<slug>.html` | 每篇文章一页，带上一篇/下一篇 |

## 加一篇新文章

1. 在 `posts/` 新建一个 `.md`，文件名建议 `YYYY-MM-DD-<slug>.md`：
   ```markdown
   ---
   title: 标题
   date: 2026-10-24
   tag: NovaPlayer
   tagkey: novaplayer
   slug: my-new-post
   excerpt: 一两句摘要（会出现在卡片上）
   ---
   正文 markdown：支持 ## / ### 标题、**粗体**、`代码`、- 与 1. 列表、> 引用、``` 代码块、[文字](https://链接)
   ```
   tagkey 只能是 `novaplayer` / `daikin` / `toolbox` / `plan`（新增产品标签要同步改 `build.py` 的 TAGS）。
2. `python3 build.py` 重新生成 `site/`。
3. `python3 deploy.py` 部署（wrangler@3 + 保险箱里的 Cloudflare 令牌，通道同其他 Pages 站）。

改游戏/开发记录卡片：直接改 `build.py` 里的 `GAMES` / `RECORDS` 列表后重跑 build + deploy。

## 过渡动效

按 NovaPlayer 1.12.1 定版「组合」口径（2026-10-24 强化）：点开任意内部链接/卡片，新页面整页轻微放大 + 上浮淡入到位（280ms；点卡片进文章/日页用更强一档的 cardIn 带承接感，普通导航用 pageIn），退出为当前页 200ms 快速反向淡出再跳转，浏览器返回走 200ms 快速淡入。只用 transform/opacity、动画可打断（连点直接跳转）、`prefers-reduced-motion` 时全站无动画。实现：进入触发脚本 `HEAD_JS` 内联在 `<head>` 里、首帧前就给 `<html>` 打上 `anim`/`data-nav`，不依赖任何外链资源；退出拦截在 `build.py` 的 `NAV_JS`。

## 脱敏红线

博文只许写产品名、版本号、公开下载方式与公开数字（大小/哈希前后段）。
**禁止**出现：内网 IP、设备序列号/ID、配对码、任何令牌/密码、远程桌面 ID、中继地址、NAS 细节。部署前用 grep 自查一遍再发。

## 全站密码门 + 入口总汇（2026-10-28）

- 首页即入口总汇：软件图书馆、NP/筋斗时间轴、筋斗游戏、订阅后台、授权管理、大金刷机指南、私密记事本、EdgeSSH、家里服务一排（飞牛/Lucky/青龙/HA/OpenWrt，注明需飞牛开着/隧道通）。外站只链接，不改其内容。
- 全站密码门：`functions/`（Pages Functions）+ D1。中间件除 `/login`、`/setup`、`/api/login`、`/api/setup`、`/api/logout`、`/logout`、`/favicon.ico` 外一律要求有效会话，否则 302 到 `/login`。
- 密码由站长本人在 `/setup` 自设，只存 SHA-256 摘要；设好后 `/setup` 返回 404。会话 7 天，HttpOnly Cookie。
- D1 说明：账户 D1 上限 10 个已满，无法新建；复用博客已有的 blog-notepad 库（`b0a79ff2…`），门专用表 `blog_settings` / `blog_sessions`，与记事本的 `notes` / `sessions` 表不冲突。绑定经 `wrangler.toml` 的 `[[d1_databases]]`（DB）在直接上传部署时生效，已实测。
- **部署必须从本目录跑 `deploy.py`**：wrangler 只有在该目录下才会带上 `wrangler.toml` 绑定与 `functions/`；换目录跑会静默丢掉密码门。
- 大金刷机指南：`site/daikin-flash.html`（源码在 `build.py` 的 `build_guide()`），不要手改 `site/` 输出。首页 Hub 本身就是 `build()` 里的首页生成逻辑（`HUB_CARDS` / `HOME_CARDS`），同样不要手改 `site/index.html`。
- 私密记事本仍有自己的密码：进站后点记事本可能再提示一次，属正常（双重提示）。

---

## 每日限免 App 自动化（2026-11-23 上线）

`automation/` 里是每日 iOS 限免 App 的全自动流水线：每天早上自动找限免、
写博客帖、部署、发 Telegram 频道，不用人工干预。

```
Mergeek / GoFans / AppRaven / 360-reader   (找付费转免费)
  + oodata.net IAP 列表 + 内购候选发现 (AppHunt, 仅发现用)
        │  iTunes Lookup 核价 (price 0) · App Store 页查内购
        ▼
automation/pipeline.py  →  posts/<date>-free-apps.md + 图标/截图/封面
        │  python3 build.py → site/
        ▼
wrangler pages deploy (项目 devlog, 从本目录跑, 带 functions/ 门禁)
        │
        ▼
automation/tg_post.py  →  Telegram 频道 @freeapps_daily
```

- 定时：每天 09:00 CST（01:00 UTC），见 `.github/workflows/daily.yml`。
- 每 3 天清理过期应用（`cleanup.yml` + `automation/cleanup.py`）：
  复查近 7 天发过的应用价格，恢复原价的从博客帖删除、频道消息删除；
  同时删 7 天前的旧帖和图片（防 Cloudflare Pages 文件数超限）。
- 手动触发：Actions → Daily free apps → Run workflow，可传 `date` 和 `dry_run`。

### 规则（2026-11-23 实测定稿）

- 付费区**排除带内购的应用**：iTunes Lookup 没有内购字段，必须抓
  `https://apps.apple.com/us/app/id<id>` 页面查 `<dt>In-App Purchases</dt>`
  标记（裸子串 "In-App Purchases" 会误命中描述/页脚，不可用）。
- 每款都用 iTunes Lookup 核价（price 0, US），恢复原价的不要。
- 图标（artworkUrl512）和截图一律存 `.jpg`（苹果返回的是 JPEG 数据），
  经 PIL 转码统一为 JPEG。
- 支持语言取自 iTunes `languageCodesISO2A`，存
  `automation/data/<date>/languages.json`，频道按“中文优先、前 5 种＋总数，
  仅英文显示‘仅英文’”显示。
- 每天挑 2–3 款“今日极力推荐”（规则：原价高＋评分高）。
- 内购应用也要取截图（最多 4 张）；内购是开发者公开兑换码方式，
  **不是**商店直降，文案必须写清楚。
- 内购只发**公开直兑链接**（用户 2026-11-23 定：以后要发就发公开的，
  AppHunt 不要了）：`https://apps.apple.com/redeem?ctx=offercodes&id=<App ID>&code=<公开自定义兑换码>`，
  开发者在 App Store Connect 建的公开自定义码，点开直接进 App Store
  兑换页，不用登第三方。没有公开码的内购款只给 App Store 下载链接，
  不放领取链接，**绝不猜 URL、绝不编兑换码**。
  - 公开码来源（按优先级）：`automation/data/public_codes.json`（人工收录，
    如 SuperC 的 SUPERC2026）→ oodata.net IAP 列表
    （`automation/scrape.py: scrape_oodata`，聚合开发者公开码）→
    开发者官网（sellerUrl，`redeem_codes.py` 自动查）。
  - AppHunt 只用来**发现**哪些应用有免费终身内购（以及内购解锁文案），
    不产任何 AppHunt 链接、码、剩余码数。
  - 博客帖内购段有公开码时加 `- **兑换链接**：[点这里兑换](redeem 链接)`，
    发帖脚本解析后在配文末尾加 `🎟️ 兑换链接：<a href="...">点这里兑换</a>`；
    没有公开码时整行省略。
  - 内购引导语不再提 AppHunt：“点帖子里的兑换链接直接进 App Store 兑”。
- 频道格式：**宽幅横图 ＋ 结构化字段**，每款一个消息。不再用 icon＋2 图的
  media group 横滑。
  - 图片：PIL 把该款的截图（最多 4 张，不足取 2 张）横向拼成一张宽幅
    banner（截图等高 900px、16px 间距、24px 内边距、iOS 浅灰底
    #F2F2F7），存为 `assets/free-apps-<date>/banner-<appid>.jpg`
    （`automation/banner.py`，与 live 发帖脚本的 banner.py 同一版式）。
    博客每款的头图也用同一张 banner（carousel 保留）。
  - 配文（HTML 结构化字段，带 emoji 前缀，与 live 发帖脚本同一版式）：
    付费款以 `#应用限免` 开头，依次是 📁 软件名称 / 🍎 支持平台（设备 ·
    iOS 最低系统）/ 💰 软件价格（删除线原价 → **免费**）/ ⭐ 评分 /
    🌐 支持语言 / 📝 软件简介 / 📲 下载链接。内购款以 `#终身内购` 开头，
    加 🎁 内购 / 📦 剩余兑换码 / 📝 解锁内容，末尾有公开码时加
    🎟️ 兑换链接。
  - 频道里一律不放博客地址；发图间隔 4 秒，429 按 retry_after 等待重试。
- 频道里**一律不放博客地址**。
- Telegram `sendMediaGroup` **不支持** `reply_markup`（内联按钮会被静默丢掉），
  App Store 链接必须放在 caption 里：
  `📲 <a href="...">在 App Store 打开</a>`。
- 遇 Telegram 429：等 `retry_after`（或 60 秒）再补发未发完的部分；
  每条组图之间停 4 秒；`posted.json` 记录已发消息 ID，断点续发不重复。
- 限免结束时间苹果不公布，**不要编造截止日期**，只说“一般 1–3 天，尽快领”。
- 不登录 Apple ID，不买任何东西。

### 本地运行

```bash
python3 automation/pipeline.py --date 2026-11-24 --dry-run  # 只生成+构建
python3 automation/pipeline.py --date 2026-11-24            # 全流程
python3 automation/cleanup.py --dry-run
```

本地运行时 Cloudflare token 走已注册的 connector 凭据；
GitHub Actions 里走 Secrets。

### 需要的 Secrets（仓库 Settings → Secrets and variables → Actions）

| Secret | 说明 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | @FreeAppsDailyBot 的 token |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token，权限：Account `Cloudflare Pages: Edit` + `Account Settings: Read`（部署 `devlog` 项目用） |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 账户 ID |

> 注意：Cloudflare API token **不能**用现有 token 的 API 创建（当前 token
> 没有 User API Tokens 权限，POST /user/tokens 返回 403）。
> 请在 Cloudflare 控制台手动创建一个：My Profile → API Tokens →
> Create Token → 用 “Edit Cloudflare Pages” 模板，Account Resources 选
> 当前账户，然后把 token 存进上面的 Secret。

### 数据来源

- Mergeek <https://mergeek.com/free/apps>（主源；页面无 App Store ID，
  用 iTunes Search API 按精确应用名解析 ID）
- GoFans <https://gofans.cn>（详情页含 App Store 链接）
- AppRaven <https://appraven.net>（原 AppSliced；GraphQL `appsOnSale`，
  直接给 ITunesId）
- 360-reader <https://360-reader.com/paid-iphone-apps-gone-free/>
  （HTML 表格含原价和评分）
- oodata.net <https://apps.oodata.net/search/result?q=%23IAP>（IAP 列表，
  聚合开发者公开的自定义兑换码；直接给 redeem 链接）
- AppHunt <https://apphunt.app/promos>（仅发现用：哪些应用有免费终身内购
  及其解锁文案；不产任何 AppHunt 链接/码/剩余码数）
