#!/usr/bin/env python3
"""开发日志博客构建脚本。

用法: python3 build.py
- 读 posts/*.md（front matter + markdown 正文）生成:
    site/index.html        首页（入口总汇 Hub）
    site/log.html          日志（全部文章 + 标签筛选）
    site/games.html        我的游戏
    site/records.html      开发记录（各产品时间轴入口）
    site/posts/<slug>.html 每篇文章一页
加新文章: 在 posts/ 里新建一个 .md，跑一次本脚本，再跑 deploy.py。
"""
import html, os, re, shutil, sys, datetime

from plan_data import PLAN_WEEKS

ROOT = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(ROOT, "posts")
SITE = os.path.join(ROOT, "site")

TAGS = [("novaplayer", "NovaPlayer"), ("daikin", "大金固件"), ("toolbox", "IPA 工具箱"), ("plan", "接单学习")]

# ---------------- markdown (子集) ----------------

def inline(s):
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", r'<img src="\2" alt="\1" class="md-img" loading="lazy">', s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    return s

def md2html(text, fx=False, heads=None):
    # fx=False 时输出与旧版逐字一致（预览生成器 import 本函数，默认行为不动）。
    # fx=True（真站文章页）: 围栏代码保留语言并包成 .fx-code 结构；h2 加 sec-N 锚点并把纯文本标题记入 heads。
    out, i, lines, h2n = [], 0, text.strip("\n").split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("```"):
            lang = ln.strip()[3:].strip()
            buf = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1
            code = html.escape("\n".join(buf))
            if fx:
                lang_html = f'<span class="lang">{html.escape(lang)}</span>' if lang else ""
                out.append(f'<div class="fx-code"><div class="fx-code-head">{lang_html}<span class="sp"></span>'
                           f'<button class="fx-fold" type="button">折叠</button>'
                           f'<button class="fx-copy" type="button">复制</button></div>'
                           f'<div class="fx-code-body"><div class="gut"></div><pre><code>{code}</code></pre></div></div>')
            else:
                out.append("<pre><code>" + code + "</code></pre>")
            continue
        if not ln.strip():
            i += 1; continue
        m = re.match(r"^(#{2,4})\s+(.*)", ln)
        if m:
            lvl = len(m.group(1))
            if lvl == 2 and fx:
                h2n += 1
                plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", m.group(2))
                plain = plain.replace("**", "").replace("__", "").replace("`", "")
                if heads is not None:
                    heads.append(plain)
                out.append(f'<h2 id="sec-{h2n}">{inline(m.group(2))}</h2>'); i += 1; continue
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>"); i += 1; continue
        if ln.strip() == "---":
            out.append("<hr>"); i += 1; continue
        if ln.startswith("> "):
            buf = []
            while i < len(lines) and lines[i].startswith("> "):
                buf.append(lines[i][2:]); i += 1
            out.append("<blockquote>" + inline(" ".join(buf)) + "</blockquote>"); continue
        if re.match(r"^\s*(-|\d+\.)\s+", ln):
            ordered = bool(re.match(r"^\s*\d+\.\s+", ln))
            items = []
            while i < len(lines) and re.match(r"^\s*(-|\d+\.)\s+", lines[i]):
                items.append(re.sub(r"^\s*(-|\d+\.)\s+", "", lines[i])); i += 1
            tag = "ol" if ordered else "ul"
            cls = ' class="art"' if True else ""
            out.append(f"<{tag}{cls}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        if ln.strip() == "!carousel":
            imgs = []
            i += 1
            while i < len(lines):
                m_shot = re.match(r"^\s*!\[([^\]]*)\]\(([^)\s]+)\)\s*$", lines[i])
                if not m_shot:
                    break
                imgs.append((m_shot.group(1), m_shot.group(2)))
                i += 1
            if imgs:
                inner = "".join(f'<img src="{html.escape(u)}" alt="{html.escape(a)}" class="shot-img" loading="lazy">' for a, u in imgs)
                out.append(f'<div class="shot-carousel">{inner}</div>')
            continue
        m_img = re.match(r"^\s*!\[([^\]]*)\]\(([^)\s]+)\)\s*$", ln)
        if m_img:
            out.append(f'<figure class="md-figure"><img src="{html.escape(m_img.group(2))}" alt="{html.escape(m_img.group(1))}" class="md-img" loading="lazy"></figure>')
            i += 1; continue
        m_vid = re.match(r"^\s*!video\[([^\]]*)\]\(([^)\s]+)\)\s*$", ln)
        if m_vid:
            # 只放行 YouTube（watch / youtu.be / embed），取 11 位视频 ID；其它地址不嵌 iframe。
            vid = re.search(r"(?:v=|youtu\.be/|/embed/)([A-Za-z0-9_-]{11})", m_vid.group(2))
            if vid:
                t = re.search(r"[?&]t=(\d+)", m_vid.group(2))
                src = f"https://www.youtube.com/embed/{vid.group(1)}" + (f"?start={t.group(1)}" if t else "")
                out.append(f'<figure class="md-video"><div class="video-wrap"><iframe src="{src}" title="{html.escape(m_vid.group(1))}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen loading="lazy"></iframe></div><figcaption>{html.escape(m_vid.group(1))}</figcaption></figure>')
            else:
                out.append("<p>" + inline(m_vid.group(1) + " " + m_vid.group(2)) + "</p>")
            i += 1; continue
        buf = [ln]; i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{2,4}\s|---$|> |```|!video\[|\s*(-|\d+\.)\s+)", lines[i]):
            buf.append(lines[i]); i += 1
        out.append("<p>" + inline(" ".join(buf)) + "</p>")
    return "\n".join(out)

def load_posts():
    posts = []
    for fn in sorted(os.listdir(POSTS)):
        if not fn.endswith(".md"): continue
        raw = open(os.path.join(POSTS, fn), encoding="utf-8").read()
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
        if not m: sys.exit(f"front matter 缺失: {fn}")
        meta = {}
        for line in m.group(1).split("\n"):
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
        heads = []
        meta["body"] = md2html(m.group(2), fx=True, heads=heads)
        meta["heads"] = heads
        meta["chars"] = len(re.sub(r"<[^>]+>", "", meta["body"]))
        meta["minutes"] = max(1, round(meta["chars"] / 400))
        meta["file"] = fn
        posts.append(meta)
    posts.sort(key=lambda p: (p["date"], p["file"]), reverse=True)
    return posts

# ---------------- 模板 ----------------

CSS = """
:root{
  --bg:#05070a;
  --gold:#c9a962; --gold-hi:#e8cf9f; --gold-dim:rgba(201,169,106,.30);
  --warm:#f0ead9; --muted:#9aa294; --faint:#6d7466;
  --card-brd:rgba(201,169,106,.24);
  --green:#57c98a; --teal:#4fc4b5; --amber:#e0a93e; --slate:#93a5bd;
}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  font-family:"PingFang SC","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif;
  color:var(--warm); min-height:100vh;
  background:linear-gradient(180deg,#0b0f16 0%, #070a10 42%, #05070a 78%, #04060a 100%);
  background-attachment:fixed;
}
a{color:inherit}
.topbar{
  position:sticky;top:0;z-index:50;display:flex;align-items:center;gap:13px;
  padding:11px 22px;background:rgba(6,8,11,.62);
  backdrop-filter:blur(16px) saturate(1.3);-webkit-backdrop-filter:blur(16px) saturate(1.3);
  border-bottom:1px solid var(--gold-dim);
}
.topbar .mark{
  width:38px;height:38px;border-radius:50%;flex:0 0 auto;
  border:1px solid var(--gold);box-shadow:0 0 16px rgba(201,169,106,.35);
  display:flex;align-items:center;justify-content:center;
  font-family:"Songti SC","Noto Serif SC","STSong",serif;font-size:19px;font-weight:700;color:var(--gold-hi);
  background:radial-gradient(circle at 35% 30%, rgba(232,207,159,.22), rgba(201,169,106,.05));
}
.topbar .t{
  font-family:"Songti SC","Noto Serif SC","STSong",serif;
  font-size:22px;font-weight:700;letter-spacing:.06em;white-space:nowrap;
  background:linear-gradient(180deg,#f4e3bb,#cfa963);
  -webkit-background-clip:text;background-clip:text;color:transparent;
}
.topbar nav{margin-left:auto;display:flex;gap:4px;align-items:center}
.topbar nav a{
  color:var(--muted);text-decoration:none;font-size:14px;letter-spacing:.06em;
  padding:7px 13px;border-radius:999px;border:1px solid transparent;
}
.topbar nav a:hover{color:var(--gold-hi)}
.topbar nav a.on{color:var(--gold-hi);border-color:var(--gold-dim);background:rgba(201,169,106,.09)}
@media (max-width:640px){
  .topbar{padding:10px 12px;gap:8px;flex-wrap:wrap}
  .topbar nav{margin-left:0;width:100%;justify-content:space-between}
  .topbar .t{font-size:17px}
  .topbar nav{gap:1px}
  .topbar nav a{padding:6px 7px;font-size:12.5px;letter-spacing:.02em;white-space:nowrap}
  .topbar .mark{width:32px;height:32px;font-size:16px}
}
.wrap{max-width:1060px;margin:0 auto;padding:0 22px}
@media (max-width:640px){ .wrap{padding:0 15px} }
.hero{padding:50px 0 6px}
.hero h1{
  font-family:"Songti SC","Noto Serif SC","STSong",serif;
  font-size:clamp(32px,5.2vw,50px);font-weight:700;letter-spacing:.05em;
  background:linear-gradient(180deg,#f7ead0,#d3ab66);
  -webkit-background-clip:text;background-clip:text;color:transparent;
}
.hero p{margin-top:12px;color:var(--muted);font-size:15px;line-height:1.75;letter-spacing:.03em;max-width:720px}
.hero p b{color:var(--gold-hi);font-weight:600}
.sec-title{
  margin:38px 0 4px;font-size:12.5px;letter-spacing:.30em;color:var(--gold);
  display:flex;align-items:center;gap:14px;
}
.sec-title::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--gold-dim),transparent)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px;margin-top:14px}
.grid2{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:16px;margin-top:14px}
@media (max-width:640px){ .grid,.grid2{grid-template-columns:1fr} }
.card{
  display:block;text-decoration:none;border-radius:18px;padding:20px 22px;
  background:linear-gradient(135deg, rgba(255,255,255,.075), rgba(255,255,255,.024) 55%, rgba(201,169,106,.045));
  border:1px solid var(--card-brd);
  backdrop-filter:blur(14px) saturate(1.25);-webkit-backdrop-filter:blur(14px) saturate(1.25);
  box-shadow:0 14px 34px rgba(0,0,0,.38), inset 0 1px 0 rgba(255,255,255,.09);
  transition:transform .18s ease, border-color .18s ease;
}
a.card:hover{transform:translateY(-2px);border-color:rgba(201,169,106,.5)}
a.card:active{transform:scale(.99)}
.card .row1{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.pname{
  font-family:"Songti SC","Noto Serif SC",serif;font-size:21px;font-weight:700;color:#fdf6e3;letter-spacing:.03em;
}
.pdesc{margin-top:9px;font-size:13.5px;line-height:1.7;color:var(--muted)}
.plink{margin-top:13px;font-size:12.5px;color:var(--gold-hi);letter-spacing:.05em}
.tagchip{
  font-size:11.5px;color:var(--gold-hi);letter-spacing:.05em;
  border:1px solid var(--gold-dim);border-radius:999px;padding:3px 11px;background:rgba(201,169,106,.08);
}
.st{font-size:12px;display:inline-flex;align-items:center;gap:6px;color:var(--muted);
    border:1px solid rgba(255,255,255,.14);border-radius:999px;padding:3px 10px;background:rgba(255,255,255,.04)}
.st i{width:7px;height:7px;border-radius:50%;display:inline-block}
.st-rel i{background:var(--green);box-shadow:0 0 8px var(--green)}
.st-acc i{background:var(--teal);box-shadow:0 0 8px var(--teal)}
.st-dev i{background:var(--amber);box-shadow:0 0 8px var(--amber);animation:pulse 1.6s infinite}
.st-plan i{background:var(--slate);box-shadow:0 0 8px var(--slate)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
.post-date{font-size:12.5px;color:#cdbd97;letter-spacing:.05em}
.post-title{margin-top:8px;font-size:17.5px;font-weight:650;line-height:1.5;color:#fdf6e3;letter-spacing:.02em}
.post-ex{margin-top:8px;font-size:13.5px;line-height:1.7;color:var(--muted)}
.filters{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}
.fbtn{
  font:inherit;font-size:13px;letter-spacing:.05em;cursor:pointer;color:var(--muted);
  border:1px solid rgba(255,255,255,.15);border-radius:999px;padding:6px 15px;background:rgba(255,255,255,.03);
}
.fbtn:hover{color:var(--gold-hi)}
.fbtn.on{color:#2a1e08;font-weight:650;background:linear-gradient(180deg,#ecd096,#c49a58);border-color:transparent}
.hidden{display:none !important}
.empty-note{margin-top:20px;color:var(--faint);font-size:13.5px}
/* ---------- 日志搜索（zoe.loc.cc 同款：实时过滤 + 标签交集 + 空状态） ---------- */
.log-search{position:relative;max-width:520px;margin-top:18px}
.log-search input{
  width:100%;font:inherit;font-size:14px;color:var(--warm);outline:none;
  background:rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.16);border-radius:999px;
  padding:10px 40px 10px 18px;
}
.log-search input:focus{border-color:rgba(201,169,106,.6)}
.log-search input::placeholder{color:var(--faint)}
.log-search .clear{
  position:absolute;right:8px;top:50%;transform:translateY(-50%);
  width:26px;height:26px;border-radius:50%;border:none;cursor:pointer;
  font:inherit;font-size:16px;line-height:1;color:var(--muted);
  background:rgba(255,255,255,.08);
}
.log-search .clear:hover{color:var(--gold-hi);background:rgba(201,169,106,.18)}
/* ---------- 首页状态徽章 ---------- */
.hub-badges{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}
.hub-badge{
  font-size:12.5px;color:var(--muted);letter-spacing:.04em;
  border:1px solid rgba(201,169,106,.30);border-radius:999px;padding:4px 13px;
  background:rgba(201,169,106,.07);
}
.hub-badge b{color:var(--gold-hi);font-weight:650}
.hist-list{list-style:none;margin:14px 0 0;padding:0;border-top:1px solid var(--card-brd)}
.hist-item{display:flex;justify-content:space-between;gap:12px;padding:10px 2px;border-bottom:1px solid rgba(201,169,106,.12)}
.hist-item a{color:#e8ddc0;text-decoration:none;font-size:14.5px;line-height:1.5}
.hist-item a:hover{color:var(--gold-hi)}
.hist-date{flex:none;color:var(--faint);font-size:13px}
/* ---------- 文章页 ---------- */
.article{max-width:780px;margin:0 auto;padding:38px 0 10px}
.article .backlink{font-size:13px;color:var(--muted);text-decoration:none;letter-spacing:.05em}
.article .backlink:hover{color:var(--gold-hi)}
.article h1{
  margin-top:16px;font-family:"Songti SC","Noto Serif SC",serif;
  font-size:clamp(26px,4.4vw,36px);font-weight:700;line-height:1.4;letter-spacing:.03em;color:#fdf6e3;
}
.article .ameta{margin-top:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.article .body{margin-top:26px;font-size:15.5px;line-height:1.95;color:#e9e2d0}
.article .body p{margin:0 0 16px}
.article .body h2{
  margin:30px 0 12px;font-size:19px;font-weight:700;color:#fdf6e3;letter-spacing:.03em;
  padding-left:12px;border-left:3px solid var(--gold);
}
.article .body h3{margin:24px 0 10px;font-size:16.5px;font-weight:700;color:var(--gold-hi)}
.article .body ul.art,.article .body ol.art{margin:0 0 16px;padding-left:4px;list-style:none}
.article .body ol.art{counter-reset:li}
.article .body li{position:relative;padding:4px 0 4px 18px}
.article .body ul.art li::before{content:"";position:absolute;left:2px;top:14px;width:5px;height:5px;border-radius:50%;background:var(--gold-hi);box-shadow:0 0 6px rgba(232,207,159,.8)}
.article .body ol.art li::before{content:counter(li) ".";counter-increment:li;position:absolute;left:0;top:4px;color:var(--gold-hi);font-size:13.5px}
.article .body ol.art li{padding-left:26px}
.article .body b{color:#ffe9b8;font-weight:650}
.article .body code{
  font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:.9em;
  background:rgba(201,169,106,.12);border:1px solid rgba(201,169,106,.22);
  border-radius:6px;padding:1px 6px;color:var(--gold-hi);
}
.article .body pre{
  background:rgba(0,0,0,.45);border:1px solid rgba(201,169,106,.22);border-radius:12px;
  padding:14px 16px;overflow-x:auto;margin:0 0 16px;
}
.article .body pre code{background:none;border:none;padding:0;color:#e9e2d0;font-size:13px;line-height:1.7}
.article .body blockquote{
  margin:0 0 16px;padding:10px 16px;border-left:3px solid var(--gold);
  background:rgba(201,169,106,.06);border-radius:0 12px 12px 0;color:var(--muted);
}
.article .body hr{border:none;height:1px;background:linear-gradient(90deg,transparent,var(--gold-dim),transparent);margin:26px 0}
.article .body a{color:var(--gold-hi)}
.anav{max-width:780px;margin:34px auto 0;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
.anav a{font-size:13.5px;color:var(--muted);text-decoration:none}
.anav a:hover{color:var(--gold-hi)}
footer{max-width:1060px;margin:0 auto;padding:34px 22px 46px;color:var(--faint);font-size:12.5px;line-height:1.9;letter-spacing:.03em}
footer .rule{height:1px;background:linear-gradient(90deg,transparent,rgba(201,169,106,.4),transparent);margin-bottom:16px}
/* ---------- 学习计划 ---------- */
.mschip{font-size:11.5px;color:#2a1e08;font-weight:700;letter-spacing:.05em;
  border-radius:999px;padding:3px 11px;background:linear-gradient(180deg,#ecd096,#c49a58)}
.daycheck{list-style:none}
.daycheck li{position:relative;padding:4px 0 4px 26px}
.daycheck li::before{content:"☐";position:absolute;left:2px;top:3px;color:var(--gold-hi);font-size:15px}
/* ---------- 视觉定版（2026-10-24 用户拍板）：B 深空竖渐变 + 点缀包全开，原样移植自 preview-bg.html 的 theme-b 与 deco-on 实现 ---------- */
body::before{
  content:"";position:fixed;inset:0;z-index:1;pointer-events:none;opacity:.5;
  background-image:
    linear-gradient(rgba(255,255,255,.028) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.028) 1px, transparent 1px);
  background-size:46px 46px;
}
.hero h1::after{
  content:"";display:block;width:58px;height:3px;border-radius:99px;margin-top:16px;
  background:linear-gradient(90deg,var(--gold-hi),rgba(201,169,106,.12));
  box-shadow:0 0 10px rgba(201,169,106,.35);
}
.sec-title::before{
  content:"";width:7px;height:7px;flex:0 0 auto;transform:rotate(45deg);border-radius:1.5px;
  background:linear-gradient(135deg,var(--gold-hi),var(--gold));
  box-shadow:0 0 8px rgba(201,169,106,.55);
}
.card{
  border-color:rgba(201,169,106,.40);
  box-shadow:0 14px 34px rgba(0,0,0,.38), inset 0 1px 0 rgba(255,255,255,.09),
             0 0 0 1px rgba(232,207,159,.05), 0 8px 26px rgba(201,169,106,.07);
}
a.card:hover{
  border-color:rgba(232,207,159,.62);
  box-shadow:0 16px 38px rgba(0,0,0,.42), inset 0 1px 0 rgba(255,255,255,.10),
             0 0 0 1px rgba(232,207,159,.10), 0 10px 30px rgba(201,169,106,.13);
}
.st{
  background:linear-gradient(180deg, rgba(255,255,255,.10), rgba(255,255,255,.02));
  border-color:rgba(255,255,255,.22);
}
.tagchip{
  background:linear-gradient(180deg, rgba(232,207,159,.17), rgba(201,169,106,.06));
  border-color:rgba(201,169,106,.42);
}
.fbtn{background:linear-gradient(180deg, rgba(255,255,255,.055), rgba(255,255,255,.015))}
.fbtn.on{background:linear-gradient(180deg,#f2d9a4,#bd9250)}
.orn{display:flex;align-items:center;gap:12px;margin:36px 0 0}
.orn::before,.orn::after{content:"";flex:1;height:1px}
.orn::before{background:linear-gradient(90deg,transparent,rgba(201,169,106,.45))}
.orn::after{background:linear-gradient(90deg,rgba(201,169,106,.45),transparent)}
.orn span{
  width:6px;height:6px;border-radius:1.5px;transform:rotate(45deg);flex:0 0 auto;
  background:linear-gradient(135deg,var(--gold-hi),var(--gold));
  box-shadow:0 0 9px rgba(201,169,106,.6);
}
/* ---------- 页面过渡（NP 定版「组合」口径强化版） ----------
   进入：整页轻微放大+上浮淡入 280ms（点卡片进入更强一档、带承接感）；返回：快速淡入 200ms。
   退出：点击内部链接先给当前页 200ms 快速反向淡出再跳转。只用 transform/opacity，可打断。 */
main{display:block}
html.anim main{animation:pageIn .28s ease both}
html.anim[data-nav="card"] main{animation:cardIn .28s cubic-bezier(.22,.8,.30,1) both;transform-origin:50% 0}
html.anim[data-nav="back"] main{animation:backIn .2s ease both}
@keyframes pageIn{from{opacity:0;transform:scale(.986) translateY(6px)}to{opacity:1;transform:none}}
@keyframes cardIn{from{opacity:0;transform:scale(.965) translateY(12px)}to{opacity:1;transform:none}}
@keyframes backIn{from{opacity:0;transform:scale(.994)}to{opacity:1;transform:none}}
main.leaving{opacity:0;transform:scale(.99);transition:opacity .2s ease,transform .2s ease;pointer-events:none}
@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{animation:none !important;transition:none !important}
  html{scroll-behavior:auto}
}
"""

HEAD_JS = """
<script>
(function(){
  // 进入动画的触发必须在首帧前就位：本脚本内联在 <head>，同步执行，不等任何外链资源。
  try {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var nav = 'page';
    if (sessionStorage.getItem('dl-from-card')) { nav = 'card'; sessionStorage.removeItem('dl-from-card'); }
    var nt = performance.getEntriesByType && performance.getEntriesByType('navigation')[0];
    if (nt && nt.type === 'back_forward') nav = 'back';
    document.documentElement.classList.add('anim');
    document.documentElement.setAttribute('data-nav', nav);
  } catch(e){}
})();
</script>
"""

NAV_JS = """
<script>
(function(){
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) return;
  // 进入侧动画由 <head> 内联脚本在首帧前触发；这里只管退出侧：
  // 点内部链接 -> 当前页 200ms 快速反向淡出 -> 跳转（连点可打断：第二次点击立刻跳）。
  var main = document.querySelector('main'), timer = null;
  document.addEventListener('click', function(e){
    var a = e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button) return;
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#' || a.target === '_blank') return;
    var url;
    try { url = new URL(a.href, location.href); } catch(err){ return; }
    if (url.origin !== location.origin) return;
    if (url.pathname === location.pathname && url.search === location.search) return;
    e.preventDefault();
    try { sessionStorage.setItem('dl-from-card', a.classList.contains('card') ? '1' : ''); if(!a.classList.contains('card')) sessionStorage.removeItem('dl-from-card'); } catch(err){}
    if (!main) { location.href = a.href; return; }
    if (timer) { clearTimeout(timer); location.href = a.href; return; } // 可打断：连点直接跳
    main.classList.add('leaving');
    timer = setTimeout(function(){ location.href = a.href; }, 180);
  }, true);
  window.addEventListener('pageshow', function(ev){
    if (ev.persisted && main) { main.classList.remove('leaving'); }
  });
})();
</script>
"""

# ---------------- 特效落地（2026-10-24 用户点头） ----------------
# 配色硬约束：只用真站 CSS 已有的 RGB 三元组（金 201,169,106 / 金亮 232,207,159 /
# 暖白 240,234,217 / 纸白 253,246,227 / 深底 5,7,10 与 11,15,22 / 白 / 黑），透明度沿用站内惯例；
# 预览里新出现的深灰蓝 (24,26,34)、(10,12,18)、#12141c、#1a1d27 已改回 #0b0f16 系。
# 不含点赞、智能助手、评论区（见任务书：不上真站）。
FX_CSS = """
/* ---------- 三栏布局 ---------- */
.fx-layout{
  display:grid;grid-template-columns:238px minmax(0,1fr) 266px;gap:22px;
  max-width:1290px;margin:0 auto;padding:0 22px;
}
.fx-left,.fx-right{display:flex;flex-direction:column;gap:16px;align-self:start}
.fx-left{position:sticky;top:74px}
.fx-right{position:sticky;top:74px}
.fx-mod{
  border-radius:16px;padding:16px 18px;
  background:linear-gradient(135deg, rgba(255,255,255,.06), rgba(255,255,255,.02) 55%, rgba(201,169,106,.04));
  border:1px solid var(--card-brd);
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
  box-shadow:0 12px 28px rgba(0,0,0,.32);
}
.fx-mod h4{font-size:13px;letter-spacing:.22em;color:var(--gold);margin-bottom:10px}
.fx-mod p,.fx-mod li{font-size:13px;line-height:1.75;color:var(--muted)}
.fx-mod ul{list-style:none}
@media(max-width:1080px){
  .fx-layout{grid-template-columns:210px minmax(0,1fr)}
  .fx-right{display:none}
}
@media(max-width:820px){
  .fx-layout{grid-template-columns:1fr;padding:0 15px}
  .fx-left{display:none}
}
/* ---------- 目录 ---------- */
.fx-toc a{
  display:block;text-decoration:none;font-size:13.5px;line-height:1.6;color:var(--muted);
  padding:7px 10px;border-left:2px solid transparent;border-radius:0 8px 8px 0;
}
.fx-toc a:hover{color:var(--gold-hi)}
.fx-toc a.on{color:var(--gold-hi);border-left-color:var(--gold);background:rgba(201,169,106,.08)}
.fx-tocbtn{
  display:none;position:fixed;right:18px;bottom:18px;z-index:60;align-items:center;gap:6px;
  font:inherit;font-size:13.5px;color:#2a1e08;font-weight:700;cursor:pointer;
  background:linear-gradient(180deg,#ecd096,#c49a58);border:none;border-radius:999px;
  padding:11px 18px;box-shadow:0 10px 26px rgba(0,0,0,.45);
}
@media(max-width:820px){ .fx-tocbtn{display:flex} }
.fx-tocpanel{
  position:fixed;right:16px;bottom:72px;z-index:61;width:288px;max-height:62vh;overflow:auto;
  border-radius:16px;padding:14px 16px;
  background:linear-gradient(160deg, rgba(11,15,22,.97), rgba(5,7,10,.97));
  border:1px solid rgba(201,169,106,.45);box-shadow:0 18px 44px rgba(0,0,0,.55);
  opacity:0;transform:translateY(12px);pointer-events:none;transition:opacity .18s ease,transform .18s ease;
}
.fx-tocpanel.open{opacity:1;transform:none;pointer-events:auto}
.fx-tocpanel h4{font-size:13px;letter-spacing:.22em;color:var(--gold);margin-bottom:8px}
/* ---------- 摘要卡 ---------- */
.fx-summary{
  border-radius:16px;padding:18px 20px;margin-bottom:24px;
  background:linear-gradient(135deg, rgba(201,169,106,.13), rgba(201,169,106,.04));
  border:1px solid rgba(201,169,106,.42);
  box-shadow:0 12px 28px rgba(0,0,0,.30), inset 0 1px 0 rgba(255,255,255,.07);
}
.fx-summary .lbl{font-size:12px;letter-spacing:.28em;color:var(--gold)}
.fx-summary p{margin-top:9px;font-size:14.5px;line-height:1.85;color:#f0ead9}
.fx-summary .meta{margin-top:11px;font-size:12.5px;color:var(--muted);letter-spacing:.04em}
/* ---------- 洞察图谱 ---------- */
.fx-insight{border:1px solid var(--card-brd);border-radius:16px;margin-bottom:24px;overflow:hidden;
  background:linear-gradient(135deg, rgba(255,255,255,.05), rgba(255,255,255,.015))}
.fx-insight button.head{
  width:100%;display:flex;justify-content:space-between;align-items:center;cursor:pointer;
  font:inherit;font-size:14.5px;font-weight:650;color:var(--gold-hi);letter-spacing:.04em;
  background:none;border:none;padding:15px 20px;text-align:left;
}
.fx-insight button.head .arr{transition:transform .18s ease;color:var(--gold)}
.fx-insight.open button.head .arr{transform:rotate(180deg)}
.fx-insight .body{display:none;padding:2px 20px 18px}
.fx-insight.open .body{display:block}
.fx-chain{list-style:none;border-left:2px solid rgba(201,169,106,.35);margin-left:6px;padding-left:0}
.fx-chain li{position:relative;padding:8px 0 8px 20px;font-size:13.5px;line-height:1.7;color:var(--muted)}
.fx-chain li::before{content:"";position:absolute;left:-6px;top:15px;width:9px;height:9px;
  transform:rotate(45deg);border-radius:2px;background:linear-gradient(135deg,var(--gold-hi),var(--gold));
  box-shadow:0 0 8px rgba(201,169,106,.6)}
.fx-chain li b{color:#f0ead9;font-weight:650}
/* ---------- 代码块增强 ---------- */
.fx-code{margin:0 0 18px;border:1px solid rgba(201,169,106,.30);border-radius:12px;overflow:hidden;
  background:rgba(0,0,0,.45)}
.fx-code-head{
  display:flex;align-items:center;gap:10px;padding:9px 14px;
  background:rgba(201,169,106,.08);border-bottom:1px solid rgba(201,169,106,.20);
}
.fx-code-head .lang{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:var(--gold-hi);letter-spacing:.06em}
.fx-code-head .sp{flex:1}
.fx-code-head button{
  font:inherit;font-size:12px;color:var(--muted);cursor:pointer;
  background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.14);border-radius:999px;padding:4px 12px;
}
.fx-code-head button:hover{color:var(--gold-hi);border-color:var(--gold-dim)}
.fx-code-body{display:flex;align-items:stretch}
.fx-code-body .gut{
  flex:0 0 auto;padding:14px 10px 14px 14px;text-align:right;user-select:none;
  font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px;line-height:1.7;color:var(--faint);
  border-right:1px solid rgba(201,169,106,.18);background:rgba(255,255,255,.02);
}
.fx-code-body pre{flex:1;min-width:0;margin:0 !important;border:none !important;background:none !important;
  padding:14px 16px !important;overflow-x:auto}
/* ---------- 文章内图片 ---------- */
.md-figure{margin:0 0 18px;text-align:center}
.md-figure .md-img{max-width:100%;height:auto;border-radius:12px;border:1px solid rgba(201,169,106,.25)}
/* ---------- App 预览图横向滑动（仿 App Store） ---------- */
.shot-carousel{display:flex;gap:12px;overflow-x:auto;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;padding:4px 2px 14px;margin:0 0 18px;scrollbar-width:thin}
.shot-carousel .shot-img{flex:0 0 auto;scroll-snap-align:start;height:340px;width:auto;max-width:78vw;border-radius:14px;border:1px solid rgba(201,169,106,.25)}
.shot-carousel::-webkit-scrollbar{height:6px}
.shot-carousel::-webkit-scrollbar-thumb{background:rgba(201,169,106,.4);border-radius:3px}
p .md-img{max-width:100%;height:auto;border-radius:12px;border:1px solid rgba(201,169,106,.25)}
/* ---------- 文章内视频 ---------- */
.md-video{margin:0 0 18px}
.md-video .video-wrap{position:relative;width:100%;aspect-ratio:16/9;background:#000;border-radius:12px;overflow:hidden;border:1px solid rgba(201,169,106,.25)}
.md-video .video-wrap iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
.md-video figcaption{margin-top:8px;font-size:13px;color:var(--faint);text-align:center}
.fx-code.collapsed .fx-code-body{max-height:196px;overflow:hidden;position:relative}
.fx-code.collapsed .fx-code-body::after{content:"";position:absolute;left:0;right:0;bottom:0;height:52px;
  background:linear-gradient(180deg,transparent,rgba(0,0,0,.75));pointer-events:none}
/* ---------- 搜索 ---------- */
.fx-search{position:relative}
.fx-search input{
  width:100%;font:inherit;font-size:13.5px;color:var(--warm);outline:none;
  background:rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.16);border-radius:999px;padding:10px 16px;
}
.fx-search input:focus{border-color:rgba(201,169,106,.6)}
.fx-results{display:none;position:absolute;left:0;right:0;top:44px;z-index:30;border-radius:12px;overflow:hidden;
  background:#0b0f16;border:1px solid rgba(201,169,106,.4);box-shadow:0 16px 36px rgba(0,0,0,.5)}
.fx-results.open{display:block}
.fx-results a{display:block;text-decoration:none;padding:11px 14px;border-bottom:1px solid rgba(255,255,255,.07)}
.fx-results a:last-child{border-bottom:none}
.fx-results a:hover{background:rgba(201,169,106,.10)}
.fx-results .t{font-size:13.5px;color:#fdf6e3}
.fx-results .s{font-size:12px;color:var(--muted);margin-top:2px}
/* ---------- toast ---------- */
.fx-toast{
  position:fixed;left:50%;bottom:32px;z-index:80;transform:translateX(-50%) translateY(16px);
  background:#0b0f16;border:1px solid rgba(201,169,106,.5);color:var(--gold-hi);
  font-size:13.5px;padding:11px 22px;border-radius:999px;box-shadow:0 14px 34px rgba(0,0,0,.5);
  opacity:0;pointer-events:none;transition:opacity .2s ease,transform .2s ease;white-space:nowrap;
}
.fx-toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
"""

# ---------------- 装饰升级（2026-10-24 用户点头落站；与预览站 devlog-deco-preview 一致） ----------------
# 做法：DECO_CSS 并入 page() 的 <style>；decorate_root / decorate_article 在生成时
# 直接插入横幅与封面节点（与预览的后处理正则逐字一致），不再事后改 site/。
# 图片源位：devlog/assets/（预览压缩版），build() 起手拷进 site/assets/。
# 无专属图的卡用 CSS 手绘封面（.glyph + ◆），不额外配图。
DECO_CSS = """
/* ---------- 装饰升级（纯加法；原站 CSS/JS 一律未动） ---------- */
body::after{
  content:"";position:fixed;inset:0;z-index:0;pointer-events:none;
  background:
    radial-gradient(640px 340px at 82% -60px, rgba(201,169,106,.10), transparent 70%),
    radial-gradient(520px 300px at 8% 22%, rgba(201,169,106,.05), transparent 70%);
}
.deco-banner{
  position:relative;margin:0 0 24px;border-radius:18px;overflow:hidden;
  border:1px solid rgba(201,169,106,.38);aspect-ratio:21/8;
  box-shadow:0 18px 40px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.10);
}
.deco-banner img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block}
.deco-banner::after{
  content:"";position:absolute;inset:0;
  background:linear-gradient(180deg, rgba(5,7,10,.08) 40%, rgba(5,7,10,.55) 100%);
}
@media (max-width:640px){ .deco-banner{aspect-ratio:16/9} }
.deco-cover{
  margin:-20px -22px 16px;border-radius:17px 17px 0 0;overflow:hidden;
  aspect-ratio:16/9;border-bottom:1px solid rgba(201,169,106,.30);
  background:linear-gradient(135deg, rgba(201,169,106,.16), rgba(11,15,22,.9) 70%);
}
.deco-cover img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .35s ease}
a.card:hover .deco-cover img{transform:scale(1.045)}
.deco-cover.glyph{display:flex;align-items:center;justify-content:center}
.deco-cover.glyph span{
  font-family:"Songti SC","Noto Serif SC",serif;font-size:30px;color:rgba(232,207,159,.75);
  text-shadow:0 0 16px rgba(201,169,106,.5);
}
.deco-article-cover{
  position:relative;margin:2px 0 26px;border-radius:16px;overflow:hidden;
  border:1px solid rgba(201,169,106,.38);aspect-ratio:21/9;
  box-shadow:0 16px 36px rgba(0,0,0,.42);
}
.deco-article-cover img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block}
.deco-article-cover::after{
  content:"";position:absolute;inset:0;
  background:linear-gradient(180deg, rgba(5,7,10,.05) 55%, rgba(5,7,10,.45) 100%);
}
.deco-article-cover.glyph{display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg, rgba(201,169,106,.18), rgba(11,15,22,.95) 70%)}
.deco-article-cover.glyph span{
  font-family:"Songti SC","Noto Serif SC",serif;font-size:34px;color:rgba(232,207,159,.8);
  text-shadow:0 0 18px rgba(201,169,106,.55);
}
.article .body > p:first-of-type::first-letter{
  font-family:"Songti SC","Noto Serif SC",serif;font-size:46px;line-height:.85;
  float:left;padding:6px 10px 0 0;color:var(--gold-hi);
}
.fx-mod h4::before{content:"◆";font-size:8px;color:var(--gold);margin-right:7px;vertical-align:2px}
@media (prefers-reduced-motion: reduce){
  a.card:hover .deco-cover img{transform:none}
}
"""

TAG_COVER = {"novaplayer": "cover-novaplayer.jpg", "daikin": "cover-daikin.jpg", "toolbox": "cover-toolbox.jpg"}

def _deco_img(src):
    # 封面图总量仅约 200KB，一律即时加载：避免弱网下 lazy 导致首屏封面空白
    return f'<img src="{src}" alt="" decoding="async">'

def _glyph_cover():
    return '<div class="deco-cover glyph"><span>◆</span></div>'

def _cover_for_tag(tagkey, prefix):
    if tagkey in TAG_COVER:
        return f'<div class="deco-cover">{_deco_img(prefix + "assets/" + TAG_COVER[tagkey])}</div>'
    return _glyph_cover()

def decorate_root(html_doc):
    """根页（index/log/games/records/plan）：hero 横幅 + 卡片封面，与预览正则一致。"""
    s = html_doc
    # 1. 横幅：每个 .hero 小节顶部（每页仅一个）
    s = s.replace('<section class="hero">',
                  '<section class="hero"><div class="deco-banner">' + _deco_img("assets/hero.jpg") + '</div>', 1)
    # 2. 文章卡（带 data-tagkey）：按标签插封面；学习计划逐日卡无 data-tagkey，不插（与预览一致）
    def _postcard(m):
        tagkey, cover = m.group(1), m.group(2)
        if cover:
            return m.group(0) + f'<div class="deco-cover">{_deco_img("assets/" + cover)}</div>'
        return m.group(0) + _cover_for_tag(tagkey, "")
    s = re.sub(r'<a class="card post-card" data-tagkey="([^"]+)"(?: data-cover="([^"]+)")?[^>]*>', _postcard, s)
    # 3. 产品卡（pname 直挂）：按卡片名映射（比 href 更准：NovaPlayer 产品卡 href 是 records.html）
    def _prodcard(m):
        anchor, pname = m.group(1), m.group(2)
        if "NovaPlayer" in pname:
            cover = _cover_for_tag("novaplayer", "")
        elif "大金" in pname:
            cover = _cover_for_tag("daikin", "")
        elif "工具箱" in pname:
            cover = _cover_for_tag("toolbox", "")
        else:
            cover = _glyph_cover()
        return anchor + cover + pname
    s = re.sub(r'(<a class="card" href="[^"]+"[^>]*>)\s*(<div class="pname">[^<]+</div>)',
               _prodcard, s)
    # 记录页卡片：pname 包在 row1 里
    def _prodcard_row(m):
        anchor, row, pname = m.group(1), m.group(2), m.group(3)
        if "NovaPlayer" in pname:
            cover = _cover_for_tag("novaplayer", "")
        elif "大金" in pname:
            cover = _cover_for_tag("daikin", "")
        elif "工具箱" in pname:
            cover = _cover_for_tag("toolbox", "")
        else:
            cover = _glyph_cover()
        return anchor + cover + row
    s = re.sub(r'(<a class="card" href="[^"]+"[^>]*>)\s*(<div class="row1"><span class="pname">([^<]+)</span>)',
               _prodcard_row, s)
    # 4. 游戏卡（<div class="card">）：手绘封面
    s = re.sub(r'<div class="card">', '<div class="card">' + _glyph_cover(), s)
    return s

def decorate_article(html_doc, tagkey, cover_path=None):
    """文章页：标题上方插 21:9 封面（有单篇 cover 时优先用它，否则按 tagkey；plan 用手绘封面）。"""
    if cover_path:
        cover = f'<div class="deco-article-cover">{_deco_img("../assets/" + cover_path)}</div>'
    elif tagkey in TAG_COVER:
        cover = f'<div class="deco-article-cover">{_deco_img("../assets/" + TAG_COVER[tagkey])}</div>'
    else:
        cover = '<div class="deco-article-cover glyph"><span>◆</span></div>'
    return re.sub(r'(<article class="article"[^>]*>.*?<a class="backlink"[^>]*>.*?</a>)',
                  r'\1' + cover, html_doc, count=1, flags=re.S)

FX_JS = """
<script>
(function(){
  function toast(msg){
    var t = document.getElementById('fx-toast');
    if(!t) return;
    t.textContent = msg; t.classList.add('show');
    clearTimeout(t._h); t._h = setTimeout(function(){ t.classList.remove('show'); }, 2200);
  }
  // 目录滚动高亮 + 平滑滚动 + 移动端面板
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll('[data-toc-link]'));
  var secs = tocLinks.map(function(a){
    return document.getElementById(a.getAttribute('href').slice(1));
  }).filter(Boolean);
  if ('IntersectionObserver' in window && secs.length){
    var cur = null;
    var io = new IntersectionObserver(function(es){
      es.forEach(function(e){ if (e.isIntersecting) cur = e.target.id; });
      tocLinks.forEach(function(a){ a.classList.toggle('on', a.getAttribute('href') === '#' + cur); });
    }, {rootMargin: '-20% 0px -70% 0px'});
    secs.forEach(function(s){ io.observe(s); });
  }
  tocLinks.forEach(function(a){
    a.addEventListener('click', function(ev){
      var t = document.getElementById(a.getAttribute('href').slice(1));
      if (!t) return;
      ev.preventDefault();
      t.scrollIntoView({behavior: 'smooth', block: 'start'});
      var p = document.getElementById('fx-tocpanel');
      if (p) p.classList.remove('open');
    });
  });
  var tb = document.getElementById('fx-tocbtn');
  if (tb) tb.addEventListener('click', function(){
    document.getElementById('fx-tocpanel').classList.toggle('open');
  });
  // 洞察图谱折叠
  document.querySelectorAll('.fx-insight').forEach(function(box){
    var h = box.querySelector('button.head');
    if (h) h.addEventListener('click', function(){ box.classList.toggle('open'); });
  });
  // 代码块：行号 / 复制 / 折叠
  document.querySelectorAll('.fx-code').forEach(function(box){
    var code = box.querySelector('code');
    if (!code) return;
    var text = code.textContent.replace(/\\n$/, '');
    var n = text.split('\\n').length;
    var gut = box.querySelector('.gut');
    if (gut){
      var s = '';
      for (var i = 1; i <= n; i++) s += i + '<br>';
      gut.innerHTML = s;
    }
    var cp = box.querySelector('.fx-copy');
    if (cp) cp.addEventListener('click', function(){
      var done = function(){ cp.textContent = '已复制 ✓'; setTimeout(function(){ cp.textContent = '复制'; }, 1500); toast('代码已复制'); };
      if (navigator.clipboard && navigator.clipboard.writeText){
        navigator.clipboard.writeText(text).then(done).catch(done);
      } else { done(); }
    });
    var fd = box.querySelector('.fx-fold');
    if (fd){
      if (n <= 12){ fd.style.display = 'none'; }
      else {
        box.classList.add('collapsed'); fd.textContent = '展开';
        fd.addEventListener('click', function(){
          var c = box.classList.toggle('collapsed');
          fd.textContent = c ? '展开' : '折叠';
        });
      }
    }
  });
  // 搜索：构建期生成的全站索引 search-index.json（文章页在 posts/ 内，相对路径 ../）
  var inp = document.getElementById('fx-search-input');
  var res = document.getElementById('fx-search-results');
  if (inp && res){
    var idx = null, idxFailed = false, timer = null;
    var esc = function(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); };
    var render = function(q){
      if (!q){ res.classList.remove('open'); res.innerHTML = ''; return; }
      if (idxFailed){
        res.innerHTML = '<a><div class="t">搜索索引加载失败，请稍后重试</div></a>';
        res.classList.add('open'); return;
      }
      var hits = [];
      (idx || []).forEach(function(a){
        var inTitle = a.title.toLowerCase().indexOf(q) !== -1;
        var inEx = (a.excerpt || '').toLowerCase().indexOf(q) !== -1;
        var sec = (a.sections || []).filter(function(s){ return s.toLowerCase().indexOf(q) !== -1; });
        if (inTitle || inEx || sec.length) hits.push({a: a, s: sec[0] || ''});
      });
      if (!hits.length){
        res.innerHTML = '<a><div class="t">没有匹配的文章</div></a>';
      } else {
        res.innerHTML = hits.slice(0, 8).map(function(h){
          return '<a href="../' + esc(h.a.href) + '"><div class="t">' + esc(h.a.title) + '</div>'
            + (h.s ? '<div class="s">章节：' + esc(h.s) + '</div>' : '') + '</a>';
        }).join('');
      }
      res.classList.add('open');
    };
    inp.addEventListener('input', function(){
      clearTimeout(timer);
      timer = setTimeout(function(){
        var q = inp.value.trim().toLowerCase();
        if (!q){ render(''); return; }
        if (idx || idxFailed){ render(q); return; }
        fetch('../search-index.json').then(function(r){ return r.json(); }).then(function(j){
          idx = j; render(q);
        }).catch(function(){ idxFailed = true; render(q); });
      }, 150);
    });
    document.addEventListener('click', function(e){
      if (!e.target.closest('.fx-search')){ res.classList.remove('open'); }
    });
  }
})();
</script>
"""

def page(title, desc, active, body, base=""):
    navs = [("index.html", "首页"), ("games.html", "我的游戏"), ("records.html", "开发记录"), ("plan.html", "学习计划"), ("log.html", "日志"), ("https://softlib.hench.cc.cd/", "软件图书馆")]
    nav_html = "".join(
        (f'<a href="{h}" target="_blank" rel="noopener">{t}</a>' if h.startswith("http") else
         f'<a href="{base}{h}"{" class=\"on\"" if h == active else ""}>{t}</a>') for h, t in navs)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<style>{CSS}
{FX_CSS}
{DECO_CSS}</style>
{HEAD_JS}
</head>
<body>
<header class="topbar">
  <div class="mark">记</div>
  <div class="t">开发日志</div>
  <nav>{nav_html}</nav>
</header>
<main>
{body}
</main>
<footer>
  <div class="rule"></div>
  开发日志 · 记录每个产品做对与做错的过程。内容已脱敏，不含账号、密钥与内网信息。
</footer>
{NAV_JS}
</body>
</html>
"""

def fmt_date(d):
    y, m, dd = d.split("-")
    return f"{y}年{int(m)}月{int(dd)}日"

def post_card(p, href_prefix="posts/"):
    cov = f' data-cover="{html.escape(p["cover"])}"' if p.get("cover") else ""
    return f"""<a class="card post-card" data-tagkey="{p['tagkey']}"{cov} href="{href_prefix}{p['slug']}.html">
      <div class="row1"><span class="tagchip">{html.escape(p['tag'])}</span><span class="post-date">{fmt_date(p['date'])}</span></div>
      <div class="post-title">{html.escape(p['title'])}</div>
      <div class="post-ex">{html.escape(p['excerpt'])}</div>
    </a>"""

# NOTE: 旧首页“产品家族”卡片已由入口总汇 Hub 取代，不再使用 PRODUCTS。

GAMES = [
    ("筋斗小圣", "st-rel", "已发布 · v1.5.9", "踩云追日的休闲小游戏，复刻经典跳跃手感：蓄力、连跳、云端冲刺。",
     [("直接玩", "https://game.hench.cc.cd/jindou"), ("版本页", "https://jindou.hench.cc.cd")]),
    ("银杏村的传说", "st-acc", "样板", "传奇风 H5 样板：银杏村地图、打怪与装备的第一版可玩原型。",
     []),
    ("悟空蹦蹦蹦 2 · iOS 复刻", "st-dev", "开发中", "记忆里那款悟空跳跃游戏的 iOS 复刻：原作资源已解析，玩法与关卡还原中。",
     []),
    ("松鼠大战复刻", "st-plan", "筹备中", "童年联机对战的复刻计划：先钉玩法机制，再动手。",
     []),
]

RECORDS = [
    ("NovaPlayer 版本时间轴", "st-rel", "持续更新", "每次版本演进：版本号、日期、要点、校验值，新版在上。",
     "https://nova.hench.cc.cd"),
    ("筋斗小圣版本时间轴", "st-rel", "持续更新", "筋斗小圣的版本迭代记录，与 NovaPlayer 同一维护方式。",
     "https://jindou.hench.cc.cd"),
    ("IPA 工具箱版本页", "st-rel", "持续更新", "工具箱的版本迭代记录（v1.1.0 起）。",
     "https://ipatb-versions.pages.dev"),
    ("大金固件日志", "st-acc", "博客内", "固件没有独立时间轴，开发记录就是「大金固件」标签下的文章流。",
     "log.html?tag=daikin"),
    ("IPA 工具箱日志", "st-acc", "博客内", "试错过程在「IPA 工具箱」标签下，版本明细见版本页。",
     "log.html?tag=toolbox"),
]

def plan_day_card(d, week_name):
    ms = '<span class="mschip">里程碑</span>' if d.get("milestone") else ""
    wk = week_name.split(" · ")[0]
    return f"""<a class="card post-card" href="plan/day-{d['n']}.html">
      <div class="row1"><span class="tagchip">Day {d['n']}</span><span class="post-date">{wk}</span>{ms}</div>
      <div class="post-title">{html.escape(d['title'])}</div>
      <div class="post-ex">{html.escape(d['goal'])}</div>
    </a>"""

def plan_pages():
    """生成学习计划总览页 plan.html 与逐日页 plan/day-N.html，返回总天数。"""
    os.makedirs(os.path.join(SITE, "plan"), exist_ok=True)
    total = sum(len(w["days"]) for w in PLAN_WEEKS)
    flat = [(w, d) for w in PLAN_WEEKS for d in w["days"]]

    # ---- 总览页 ----
    sec_list = []
    for w in PLAN_WEEKS:
        cards = "\n".join(plan_day_card(d, w["name"]) for d in w["days"])
        sec_list.append(f"""
  <div class="sec-title">{html.escape(w['name'])}</div>
  <p class="empty-note" style="margin-top:10px">{html.escape(w['sub'])}</p>
  <div class="grid">{cards}</div>""")
    sections = '\n  <div class="orn"><span></span></div>'.join(sec_list)
    plan_body = f"""
<div class="wrap">
  <section class="hero">
    <h1>学习计划 · 28 天接单路线图</h1>
    <p><b>你当产品经理</b>（谈需求、报价、验收），<b>AI 当开发团队</b>（开发、测试、出包）。28 天逐日路线：每天 30–45 分钟，一张卡就是一天——目标、学什么、要点速记、练习、打卡清单都在卡里，点开就能照着做，不点外链也能学到东西。</p>
    <p>节奏：第 0 周开户门面（4 天）→ 第 1 周 AI 协作基本功 → 第 2 周接单流程演练（只看不投）→ 第 3 周投第一单 → 第 4 周复盘定型。每周最后一天是里程碑。</p>
  </section>
{sections}
  <p class="empty-note">配套阅读：日志里的《我的接单学习计划：28 天路线图》讲这份计划的来历与用法。</p>
</div>"""
    open(os.path.join(SITE, "plan.html"), "w", encoding="utf-8").write(
        decorate_root(page("开发日志 · 学习计划", "28 天接单学习计划：逐日目标、要点速记、练习与打卡。", "plan.html", plan_body)))

    # ---- 逐日页 ----
    for i, (w, d) in enumerate(flat):
        notes = "".join(f"<li>{html.escape(x)}</li>" for x in d["notes"])
        checks = "".join(f"<li>{html.escape(x)}</li>" for x in d["checks"])
        nav = '<div class="anav">'
        if i > 0:
            pd = flat[i - 1][1]
            nav += f'<a href="day-{pd["n"]}.html">← Day {pd["n"]}：{html.escape(pd["title"])}</a>'
        else:
            nav += "<span></span>"
        if i + 1 < len(flat):
            nd = flat[i + 1][1]
            nav += f'<a href="day-{nd["n"]}.html">Day {nd["n"]}：{html.escape(nd["title"])} →</a>'
        else:
            nav += "<span></span>"
        nav += "</div>"
        wk = w["name"]
        ms = ' · <span class="mschip">里程碑日</span>' if d.get("milestone") else ""
        # ---- 链接与视频：links 为 [{label, url}]；video 为 YouTube 11 位 ID 或完整链接。
        # B 站视频只放链接、不嵌 iframe；本轮 8 天均无 YouTube 视频，故 video 字段暂无使用。
        links_sec = ""
        if d.get("links") or d.get("video"):
            _items = "".join(
                f'<li><a href="{html.escape(x["url"])}" target="_blank" rel="noopener">{html.escape(x["label"])}</a></li>'
                for x in d.get("links", []))
            _vid = ""
            if d.get("video"):
                _m = re.search(r"(?:v=|youtu\.be/|/embed/)([A-Za-z0-9_-]{11})", d["video"])
                _vid_id = _m.group(1) if _m else d["video"]
                _vid = (f'<figure class="md-video"><div class="video-wrap"><iframe src="https://www.youtube.com/embed/{html.escape(_vid_id)}" title="YouTube 视频" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen loading="lazy"></iframe></div></figure>')
            _list = f'\n      <ul class="art">{_items}</ul>' if _items else ""
            links_sec = f"""
      <h2>链接与视频</h2>{_list}
      {_vid}"""
        body = f"""
<div class="wrap">
  <article class="article">
    <a class="backlink" href="../plan.html">← 返回学习计划总览</a>
    <h1>Day {d['n']} · {html.escape(d['title'])}</h1>
    <div class="ameta"><span class="tagchip">{html.escape(wk)}</span><span class="post-date">约 30–45 分钟</span>{ms}</div>
    <div class="body">
      <h2>今日目标</h2>
      <p>{html.escape(d['goal'])}</p>
      <h2>学什么</h2>
      <p>{html.escape(d['learn'])}</p>
      <h2>要点速记</h2>
      <ul class="art">{notes}</ul>
      <h2>今日练习</h2>
      <p>{html.escape(d['do'])}</p>
      <h2>打卡清单</h2>
      <ul class="daycheck">{checks}</ul>{links_sec}
    </div>
  </article>
  {nav}
</div>"""
        open(os.path.join(SITE, "plan", f"day-{d['n']}.html"), "w", encoding="utf-8").write(
            page(f"Day {d['n']} · {d['title']} · 学习计划", d["goal"], "plan.html", body, base="../"))
    return total

def build():
    posts = load_posts()
    os.makedirs(os.path.join(SITE, "posts"), exist_ok=True)
    # 装饰图片：源位 devlog/assets/ -> 生成物 site/assets/（site/ 下次构建不清理，故先清旧 assets 再拷）
    assets_dst = os.path.join(SITE, "assets")
    if os.path.isdir(assets_dst):
        shutil.rmtree(assets_dst)
    shutil.copytree(os.path.join(ROOT, "assets"), assets_dst)
    # 全站搜索索引（文章页右侧搜索框用；href 以站根计，文章页 JS 前缀 ../）
    import json
    open(os.path.join(SITE, "search-index.json"), "w", encoding="utf-8").write(
        json.dumps([{"title": p["title"], "href": f"posts/{p['slug']}.html",
                     "sections": p["heads"], "excerpt": p["excerpt"],
                     "date": p["date"], "tag": p["tag"]} for p in posts],
                   ensure_ascii=False))
    plan_total = plan_pages()

    # ---- 首页（入口总汇 Hub）----
    # Hub 就是首页生成逻辑本身：HUB_CARDS / HOME_CARDS 在文件后部定义，
    # build() 执行时已加载。不要手改 site/index.html，下次构建会覆盖它。
    hub_cards = "\n".join(_hub_card(*c) for c in HUB_CARDS)
    home_cards = "\n".join(_hub_card(*c) for c in HOME_CARDS)
    hub_body = f"""
<div class="wrap">
  <section class="hero">
    <h1>入口总汇</h1>
    <p>软件、版本时间轴、游戏、订阅、授权、刷机指南与家里服务，都在这一页。</p>
    <div class="hub-badges"><span class="hub-badge">最后更新 <b>{fmt_date(posts[0]["date"])}</b></span><span class="hub-badge">共 <b>{len(posts)}</b> 篇文章</span></div>
  </section>
  <div class="sec-title">入口</div>
  <div class="grid">{hub_cards}</div>
  <div class="orn"><span></span></div>
  <div class="sec-title">家里服务</div>
  <p class="empty-note" style="margin-top:10px">需飞牛开着、隧道通；飞牛关着时打不开是正常的。</p>
  <div class="grid2">{home_cards}</div>
  <p class="empty-note">更多分区在顶部导航。· <a href="/logout" style="color:var(--gold-hi)">退出登录</a></p>
</div>"""
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(
        page("开发日志 · 入口总汇", "博客入口总汇：软件图书馆、版本时间轴、订阅后台、授权管理、刷机指南与家里服务。", "index.html", hub_body))

    # ---- 日志 ----
    chips = '<button class="fbtn on" data-tag="all">全部</button>' + "".join(
        f'<button class="fbtn" data-tag="{k}">{v}</button>' for k, v in TAGS)
    # 日志页搜索数据：标题/摘要/标签/链接，内嵌进页面供前端原生 JS 实时过滤
    # （零依赖、单文件可跑；</ 替成 <\/ 防 JSON 里的 </script> 提前闭合 script 块）
    log_search_json = json.dumps(
        [{"slug": p["slug"], "title": p["title"], "excerpt": p["excerpt"],
          "tagkey": p["tagkey"], "href": f"posts/{p['slug']}.html"} for p in posts],
        ensure_ascii=False).replace("</", "<\\/")
    # ---- 同项目折叠：所有文章按 tagkey 分组，每组只留日期最新的一篇在主列表，
    # 其余进“历史文章”区。渲染时按已排好的顺序（日期倒序，同日按文件名倒序）自动算，
    # 以后新帖也自动折叠，不写死 slug。单篇组（组内只有一篇）不受影响。
    _seen_tag, main_posts, hist_posts = set(), [], []
    for p in posts:
        if p["tagkey"] in _seen_tag:
            hist_posts.append(p)
        else:
            _seen_tag.add(p["tagkey"])
            main_posts.append(p)
    cards = "\n".join(post_card(p) for p in main_posts)
    hist_rows = "\n".join(
        f'<li class="hist-item" data-tagkey="{p["tagkey"]}"><a href="posts/{p["slug"]}.html">{html.escape(p["title"])}</a><span class="hist-date">{fmt_date(p["date"])}</span></li>'
        for p in hist_posts)
    hist_block = (f'\n  <div class="sec-title" id="histTitle">历史文章</div>\n  <ul class="hist-list" id="histList">{hist_rows}</ul>'
                  if hist_posts else "")
    log_body = f"""
<div class="wrap">
  <section class="hero">
    <h1>日志</h1>
    <p>博文流，写的都是<b>试错</b>：试了什么 → 怎么失败 → 怎么定位 → 怎么修。点标签按产品筛选，或在搜索框里按标题、摘要实时查找。</p>
  </section>
  <div class="log-search"><input id="logSearch" type="text" placeholder="搜索文章标题或摘要…" autocomplete="off"><button class="clear hidden" id="logSearchClear" type="button" aria-label="清空搜索">×</button></div>
  <div class="filters">{chips}</div>
  <div class="grid" id="postGrid">{cards}</div>{hist_block}
  <p class="empty-note hidden" id="emptyNote">这个标签下暂时还没有文章。</p>
</div>
<script id="logSearchData" type="application/json">{log_search_json}</script>
<script>
(function(){{
  var btns = document.querySelectorAll('.fbtn'), cards = document.querySelectorAll('.post-card'), note = document.getElementById('emptyNote');
  var histItems = document.querySelectorAll('.hist-item'), histTitle = document.getElementById('histTitle'), histList = document.getElementById('histList');
  var input = document.getElementById('logSearch'), clearBtn = document.getElementById('logSearchClear');
  var data = [];
  try {{ data = JSON.parse(document.getElementById('logSearchData').textContent || '[]'); }} catch(e){{ data = []; }}
  var bySlug = {{}};
  data.forEach(function(d){{ bySlug[d.slug] = d; }});
  var curTag = 'all', curQ = '', curQRaw = '';
  function slugOf(href){{
    var m = (href || '').match(/posts\\/([^\\/]+)\\.html/);
    return m ? m[1] : '';
  }}
  function matchQ(d, q){{
    if (!q) return true;
    return ((d.title || '') + ' ' + (d.excerpt || '')).toLowerCase().indexOf(q) !== -1;
  }}
  function apply(){{
    var n = 0, hn = 0;
    cards.forEach(function(c){{
      var d = bySlug[slugOf(c.getAttribute('href'))] || {{}};
      var show = (curTag === 'all' || c.getAttribute('data-tagkey') === curTag) && matchQ(d, curQ);
      c.classList.toggle('hidden', !show); if (show) n++;
    }});
    histItems.forEach(function(h){{
      var a = h.querySelector('a');
      var d = bySlug[slugOf(a ? a.getAttribute('href') : '')] || {{}};
      var show = (curTag === 'all' || h.getAttribute('data-tagkey') === curTag) && matchQ(d, curQ);
      h.classList.toggle('hidden', !show); if (show) hn++;
    }});
    if (histTitle) histTitle.classList.toggle('hidden', hn === 0);
    if (histList) histList.classList.toggle('hidden', hn === 0);
    btns.forEach(function(b){{ b.classList.toggle('on', b.getAttribute('data-tag') === curTag); }});
    var total = n + hn;
    if (total === 0){{
      note.textContent = curQRaw ? ('没有匹配「' + curQRaw + '」的文章，换个关键词试试。') : '这个标签下暂时还没有文章。';
      note.classList.remove('hidden');
    }} else {{
      note.classList.add('hidden');
    }}
    if (clearBtn) clearBtn.classList.toggle('hidden', !curQRaw);
  }}
  function setQuery(v){{
    curQRaw = v; curQ = v.trim().toLowerCase();
    apply();
  }}
  btns.forEach(function(b){{ b.addEventListener('click', function(){{
    curTag = b.getAttribute('data-tag');
    apply();
    var url = new URL(location.href);
    if (curTag === 'all') url.searchParams.delete('tag'); else url.searchParams.set('tag', curTag);
    history.replaceState(null, '', url);
  }}); }});
  if (input) input.addEventListener('input', function(){{ setQuery(input.value); }});
  if (clearBtn) clearBtn.addEventListener('click', function(){{
    if (input) input.value = '';
    setQuery(''); if (input) input.focus();
  }});
  var params = new URLSearchParams(location.search);
  var t = params.get('tag');
  if (t) curTag = t;
  var q = params.get('q');
  if (q && input){{ input.value = q; curQRaw = q; curQ = q.trim().toLowerCase(); }}
  apply();
}})();
</script>"""
    open(os.path.join(SITE, "log.html"), "w", encoding="utf-8").write(
        decorate_root(page("开发日志 · 日志", "全部博文：软件与固件的试错记录，可按产品标签筛选。", "log.html", log_body)))

    # ---- 我的游戏 ----
    gcards = ""
    for name, st, stlabel, desc, links in GAMES:
        link_html = ""
        if links:
            link_html = '<div class="plink">' + " · ".join(
                f'<a href="{u}" target="_blank" rel="noopener" style="color:var(--gold-hi)">{t}</a>' for t, u in links) + "</div>"
        gcards += f"""<div class="card">
      <div class="row1"><span class="pname">{name}</span><span class="st {st}"><i></i>{stlabel}</span></div>
      <div class="pdesc">{desc}</div>{link_html}</div>"""
    games_body = f"""
<div class="wrap">
  <section class="hero">
    <h1>我的游戏</h1>
    <p>业余时间做的小游戏：已发布、样板、筹备中，状态见徽章。</p>
  </section>
  <div class="grid">{gcards}</div>
</div>"""
    open(os.path.join(SITE, "games.html"), "w", encoding="utf-8").write(
        decorate_root(page("开发日志 · 我的游戏", "游戏卡片：筋斗小圣、银杏村的传说、悟空蹦蹦蹦2 复刻、松鼠大战复刻。", "games.html", games_body)))

    # ---- 开发记录 ----
    rcards = ""
    for name, st, stlabel, desc, href in RECORDS:
        ext = ' target="_blank" rel="noopener"' if href.startswith("http") else ""
        rcards += f"""<a class="card" href="{href}"{ext}>
      <div class="row1"><span class="pname">{name}</span><span class="st {st}"><i></i>{stlabel}</span></div>
      <div class="pdesc">{desc}</div><div class="plink">打开 →</div></a>"""
    records_body = f"""
<div class="wrap">
  <section class="hero">
    <h1>开发记录</h1>
    <p><b>版本时间轴</b>汇总：版本号、日期、要点与校验值。日志记过程，时间轴记结果。</p>
  </section>
  <div class="grid">{rcards}</div>
</div>"""
    open(os.path.join(SITE, "records.html"), "w", encoding="utf-8").write(
        decorate_root(page("开发日志 · 开发记录", "各产品版本时间轴汇总入口。", "records.html", records_body)))

    # ---- 文章页 ----
    for idx, p in enumerate(posts):
        newer = posts[idx - 1] if idx > 0 else None
        older = posts[idx + 1] if idx + 1 < len(posts) else None
        nav = '<div class="anav">'
        nav += f'<a href="{older["slug"]}.html">← 更早：{html.escape(older["title"])}</a>' if older else "<span></span>"
        nav += f'<a href="{newer["slug"]}.html">更新：{html.escape(newer["title"])} →</a>' if newer else "<span></span>"
        nav += "</div>"
        toc_links = "".join(
            f'<a href="#sec-{i + 1}" data-toc-link>{html.escape(h)}</a>'
            for i, h in enumerate(p["heads"]))
        if p["heads"]:
            chain = "".join(f"<li><b>{html.escape(h)}</b></li>" for h in p["heads"])
            insight = (f'<div class="fx-insight"><button class="head" type="button">'
                       f'<span>洞察图谱 · 本篇章节链</span><span class="arr">▾</span></button>'
                       f'<div class="body"><ol class="fx-chain">{chain}</ol></div></div>')
            toc_left = f'<div class="fx-mod"><h4>本篇目录</h4><nav class="fx-toc">{toc_links}</nav></div>'
            toc_float = (f'<button class="fx-tocbtn" id="fx-tocbtn" type="button">☰ 目录</button>'
                         f'<div class="fx-tocpanel" id="fx-tocpanel"><h4>本篇目录</h4><nav class="fx-toc">{toc_links}</nav></div>')
        else:
            insight, toc_left, toc_float = "", "", ""
        rel = [q for q in posts if q["tagkey"] == p["tagkey"] and q["slug"] != p["slug"]]
        rel += [q for q in posts if q["tagkey"] != p["tagkey"] and q["slug"] != p["slug"]]
        rel_html = "".join(
            f'<p><a href="{q["slug"]}.html" style="color:var(--gold-hi);text-decoration:none">{html.escape(q["title"])}</a></p>'
            f'<p style="margin-top:6px;margin-bottom:14px">{html.escape(q["excerpt"])}</p>'
            for q in rel[:3])
        body = f"""
<div class="fx-layout" style="margin-top:18px">
  <aside class="fx-left">
    {toc_left}
  </aside>
  <article class="article" style="padding-top:6px">
    <a class="backlink" href="../log.html">← 返回日志</a>
    <h1>{html.escape(p['title'])}</h1>
    <div class="ameta"><span class="tagchip">{html.escape(p['tag'])}</span><span class="post-date">{fmt_date(p['date'])}</span></div>
    <div class="fx-summary">
      <div class="lbl">文章摘要</div>
      <p>{html.escape(p['excerpt'])}</p>
      <div class="meta">约 {p['minutes']} 分钟 · {p['chars']} 字 · {len(p['heads'])} 节 · 标签 {html.escape(p['tag'])}</div>
    </div>
    {insight}
    <div class="body">
{p['body']}
    </div>
    {nav}
  </article>
  <aside class="fx-right">
    <div class="fx-mod fx-search">
      <h4>站内搜索</h4>
      <input id="fx-search-input" type="text" placeholder="搜全部文章…" autocomplete="off">
      <div class="fx-results" id="fx-search-results"></div>
    </div>
    <div class="fx-mod"><h4>相关文章</h4>{rel_html}</div>
    <div class="fx-mod"><h4>标签</h4><p><a href="../log.html?tag={p['tagkey']}" style="color:var(--gold-hi)">#{html.escape(p['tag'])}</a></p></div>
  </aside>
</div>
{toc_float}
<div class="fx-toast" id="fx-toast"></div>
""" + FX_JS
        open(os.path.join(SITE, "posts", p["slug"] + ".html"), "w", encoding="utf-8").write(
            decorate_article(page(p["title"] + " · 开发日志", p["excerpt"], "log.html", body, base="../"), p["tagkey"], p.get("cover")))
    print(f"built {len(posts)} posts + plan {plan_total} days -> {SITE}")

# ---------------- 入口总汇（首页 Hub）与大金刷机指南 ----------------
# 首页 Hub 已是 build() 里的首页生成逻辑；本函数只生成大金刷机指南
# site/daikin-flash.html。只改本站源码与生成物，不动任何外站。

HUB_CARDS = [
    ("软件图书馆", "全部软件的永久下载入口：版本、大小、哈希、直链。", "https://softlib.hench.cc.cd/", True),
    ("NP 版本时间轴", "NovaPlayer 每次版本演进：版本号、日期、要点、校验值。", "https://nova.hench.cc.cd", True),
    ("筋斗版本时间轴", "筋斗小圣的版本迭代记录，与 NP 同一维护方式。", "https://jindou.hench.cc.cd", True),
    ("筋斗游戏", "踩云追日的休闲小游戏：蓄力、连跳、云端冲刺。", "https://game.hench.cc.cd/jindou", True),
    ("订阅后台", "Clash 订阅管理：加节点走管理页，订阅地址填 OpenClash。", "https://sub.hench.cc.cd/admin/332402276", True, "https://sub.hench.cc.cd/sub/332402276"),
    ("授权管理", "NOVX 授权管理前端：发码、查询与解绑（需管理口令）。", "https://license.hench.cc.cd/admin", True),
    ("大金刷机指南", "大金 AB 版传感器串口刷机：J2 接线、GPIO0 短接进 BOOT、esptool 刷 2.2.49。", "daikin-flash.html", False),
    ("解密工具", "粘贴混淆代码直接解：JS 与 Python 解压解码。", "decode.html", False),
    ("签到管理", "WeTalk／PingMe 自动签到：账号、日志与 Loon 抓取脚本。", "weping.html", False),
    ("私密记事本", "站长自用的私密记事本，有自己的密码。", "notepad.html", False),
    ("EdgeSSH", "个人 WebSSH 工作台：浏览器里直连家里的机器。", "https://ssh.hench.cc.cd", True),
    ("服务清单", "Cloudflare 在用的 Workers 与 Pages 清单。", "services.html", False),
]

HOME_CARDS = [
    ("飞牛 fnOS", "NAS 系统：Docker、文件与应用入口。", "https://fn.hench.de5.net", True),
    ("青龙", "青龙面板：定时任务与脚本管理。", "https://ql.hench.de5.net", True),
    ("Home Assistant", "智能家居中枢：设备、自动化与面板。", "https://haos.hench.de5.net", True),
]

def _hub_card(name, desc, href, ext, extra=None):
    e = ' target="_blank" rel="noopener"' if ext else ""
    if extra is None:
        return (f'<a class="card" href="{href}"{e}>\n'
                f'      <div class="pname">{name}</div><div class="pdesc">{desc}</div>'
                f'<div class="plink">打开 →</div></a>')
    eh = html.escape(href, quote=True)
    ex = html.escape(extra, quote=True)
    return (f'<div class="card" onclick="window.open(\'{eh}\',\'_blank\')" style="cursor:pointer">\n'
            f'      <div class="pname">{name}</div><div class="pdesc">{desc}</div>'
            f'<div class="plink"><a href="{eh}"{e} onclick="event.stopPropagation()">管理页 →</a>　·　<a href="{ex}"{e} onclick="event.stopPropagation()">订阅地址 →</a></div></div>')

# ---------------- 服务清单（Cloudflare 在用项目，2026-11-09 盘点） ----------------
# 数据来源：Cloudflare API 实拉（Workers 18 个、Pages 14 个，已剔除当日删除的
# tg-webdav-worker 与 10 个预览 Pages、D1 notes-db）。改清单时同步改 SERVICES_UPDATED。
# 地址口径：有自定义域名的用自定义域名，其余用 https://<名字>.hench.workers.dev
# 或 <名字>.pages.dev；简介按审计报告与项目用途写，不确定的只写通用描述。
SERVICES_UPDATED = "2026-11-09"

SERVICES_WORKERS = [
    ("cfchat", "CFChat 聊天应用：频道、Telegram 桥接与语音通话。", "https://cfchat.hench.workers.dev"),
    ("checkin-hub", "每日签到中心：V2EX、雨晨、福利吧三站自动签到与管理页。", "https://checkin-hub.hench.cc.cd/"),
    ("clash-sub", "Clash 订阅管理：节点订阅与管理页。", "https://sub.hench.cc.cd/"),
    ("luci-gate", "旁路由 LuCI 入口网关：公开访问 LuCI 的挡板。", "https://luci-gate.hench.workers.dev"),
    ("novx-license", "NOVX 授权管理：发码、验证、暂停与解绑。", "https://novx-license.hench.workers.dev/admin"),
    ("weping", "WeTalk／PingMe 自动签到：账号、日志与 Loon 抓取脚本。", "https://weping.hench.workers.dev/"),
]

SERVICES_PAGES = [
    ("devlog", "开发日志博客：本站。", "https://blog.hench.cc.cd"),
    ("softlib", "软件图书馆：全部软件的永久下载入口。", "https://softlib.hench.cc.cd"),
    ("nova-versions", "NovaPlayer 版本时间轴。", "https://nova.hench.cc.cd"),
    ("jindou-versions", "筋斗小圣版本时间轴。", "https://jindou.hench.cc.cd"),
    ("jindou-game", "筋斗小圣游戏：直接开玩。", "https://game.hench.cc.cd"),
    ("ipatb-versions", "IPA 工具箱版本页。", "https://ipa.hench.cc.cd"),
    ("script-hub", "Loon／Surge 脚本中心。", "https://script-hub-5vv.pages.dev"),
    ("otterhub", "OtterHub 服务站。", "https://tg.hench.us.ci"),
    ("serial-tool", "串口工具。", "https://serial-tool-474.pages.dev"),
]

def build_services():
    w_cards = "\n".join(_hub_card(n, d, u, True) for n, d, u in SERVICES_WORKERS)
    p_cards = "\n".join(_hub_card(n, d, u, True) for n, d, u in SERVICES_PAGES)
    body = f"""
<div class="wrap">
  <article class="article">
    <a class="backlink" href="index.html">← 返回入口总汇</a>
    <h1>服务清单</h1>
    <div class="ameta"><span class="tagchip">Cloudflare</span><span class="post-date">更新于 {SERVICES_UPDATED} · 共 {len(SERVICES_WORKERS) + len(SERVICES_PAGES)} 个项目</span></div>
    <div class="body">
      <p>在用的项目一览，点卡片直接打开。预览、测试与已删除的不在里面。</p>
      <h2>Workers（{len(SERVICES_WORKERS)}）</h2>
      <div class="grid">{w_cards}</div>
      <h2>Pages（{len(SERVICES_PAGES)}）</h2>
      <div class="grid">{p_cards}</div>
      <hr>
      <p>只列有网页界面的服务。纯接口类后端（通知、授权、同步等）是给应用调的，不在里面。</p>
    </div>
  </article>
</div>"""
    open(os.path.join(SITE, "services.html"), "w", encoding="utf-8").write(
        page("服务清单 · 开发日志", "Cloudflare 上在用的 Workers 与 Pages 清单：名字、地址与简介。", "index.html", body))
    print(f"services -> services.html ({len(SERVICES_WORKERS)} workers + {len(SERVICES_PAGES)} pages)")

def build_guide():
    guide_body = """
<div class="wrap">
  <article class="article">
    <a class="backlink" href="index.html">← 返回入口总汇</a>
    <h1>大金 AB 版传感器 · 串口刷机指南（刷 2.2.49）</h1>
    <div class="ameta"><span class="tagchip">大金固件</span><span class="post-date">AB 版 BRY88AB151K · ESP32</span></div>
    <div class="body">
      <h2>先说结论</h2>
      <p>这台设备的 OTA 曾经断过一次：对一切镜像都拒收，连正在跑的好版本重刷也被拒。当时唯一的办法是串口刷一次新版：<strong>写 app0 + 擦 otadata</strong>，之后 OTA 恢复，WiFi、HomeKit 配对与校准全部不动，<strong>不用重配</strong>。以后 OTA 再拒收一切镜像，照下面串口刷最新版 2.2.49。</p>
      <h2>为什么 OTA 坏了、为什么必须串口</h2>
      <ul class="art">
        <li>当时 OTA 拒收一切镜像（包括当前正在运行的好版本），与固件内容无关。</li>
        <li>断电重上电清不掉：问题在闪存里的 OTA 记录区（otadata 分区），不在内存状态。</li>
        <li>恢复出厂也修不好：它只抹 NVS 里的几个命名空间，<strong>不动 otadata 分区</strong>，还会丢掉 WiFi 与 HomeKit 配对——不要为 OTA 去按恢复出厂。</li>
        <li>死循环：修 OTA 的代码（2.2.30 起自带的“修复 OTA 状态”按钮）本身要先装上设备，但装的唯一通道 OTA 当时是断的。</li>
        <li>所以串口是唯一入口：绕开 OTA，把新版写进 app0、把 otadata 擦干净；装上后 OTA 恢复，以后再卡住，点设备上的修复按钮即可，不用再串口。</li>
      </ul>
      <h2>准备工作</h2>
      <ul class="art">
        <li>一根 USB-TTL 转接线（CH340 / CP2102），<strong>只用 3.3V 逻辑电平</strong>。</li>
        <li>短接工具：镊子或跳线（短接 GPIO0 两孔用）。</li>
        <li>电脑一台（装好 esptool：pip install esptool）。</li>
        <li>固件 2.2.49：firmware-slim-2249.bin，1,948,192 字节，SHA256 <code>bccec45eaf756991ca64d02dacb172bdc1d8ae5ca3d266104d79b2edc6b3f89c</code>。2.2.49 取代 2.2.48 及更早版本：三天预报按当天比对显示 今天/明天/后天，仪表盘顶部 hero 天气改成读传感器自己的和风数据（Open-Meteo 拉取已移除），mDNS（主机名 dj，http://dj.local）＋Bark 推送 IP、2.2.46 的 panic 修复与 2.2.45 的室外空气修复（AQI）保留；旧版已作废，不要刷。</li>
      </ul>
      <p>固件直链：<a href="https://github.com/aliporcins/daikin-firmware/releases/download/v2.2.49/firmware-slim-2249.bin">firmware-slim-2249.bin</a>（GitHub Release 永久链，私有仓、需 GitHub 登录态下载）。</p>
      <p>下载后先核对大小与 SHA256，对不上不要刷。</p>
      <h2>开盖，认准两个位置</h2>
      <ul class="art">
        <li><strong>刷机口 J2</strong>：板子底面，ESP32 模组正下方，3 针，左→右依次是 <strong>GND / RXD / TXD</strong>。</li>
        <li><strong>短接孔 GPIO0</strong>：板子中部，PM 金属罐右缘与 ESP32 之间，两个孔，其中一个是 GND。</li>
      </ul>
      <p><strong>注意（未实证）：</strong>J2 的实物形态（已焊针还是 bare 针孔）以上游样机照片为准、我方这台尚未开盖核实——开盖后以实物为准。没有焊针时用探针 / 鳄鱼夹抵住两孔保持接触即可。</p>
      <h2>接线</h2>
      <ul class="art">
        <li>USB-TTL 的 TX 接板子的 RXD，RX 接板子的 TXD——<strong>TX / RX 交叉</strong>，不要直连。</li>
        <li>GND 接板子的 GND。</li>
        <li><strong>只用 3.3V 逻辑，绝不要把 5V 接进 TX / RX。</strong></li>
      </ul>
      <h2>供电</h2>
      <p>刷机前，先把 <strong>Power&amp;IIC 排线插到 PCB 板上</strong>——传感器用自己的电源线束供电，不要指望 USB-TTL 给整板供电。</p>
      <h2>进 BOOT 模式</h2>
      <ol class="art">
        <li>短接 GPIO0 的两个孔（保持短接状态）。</li>
        <li>上电。</li>
        <li>看板上 LED：<strong>进入 BOOT 后板上 LED 保持不亮——这就是进 BOOT 的标志</strong>。如果 LED 正常亮起、设备正常启动，说明短接没接通，重新抵紧再试。</li>
      </ol>
      <h2>刷机（电脑上执行）</h2>
      <p>把下面命令里的串口名换成你电脑上的实际串口（Windows 如 COM3，macOS / Linux 如 /dev/ttyUSB0）：</p>
      <pre><code>esptool.py --port 串口 erase_region 0xe000 0x2000
esptool.py --port 串口 write_flash 0x10000 firmware-slim-2249.bin</code></pre>
      <ul class="art">
        <li>第一条擦 otadata 分区（地址 0xe000，大小 0x2000）：擦干净后 bootloader 默认从 app0 启动。</li>
        <li>第二条把 2.2.49 写进 app0（地址 0x10000）。</li>
      </ul>
      <h2>完成</h2>
      <ol class="art">
        <li>刷完后<strong>先去掉 GPIO0 短接</strong>，再断电重上电。</li>
        <li>设备启动后即为 2.2.49：WiFi、HomeKit 配对、校准（温度 -5.2°C / 湿度 ×1.24）全部保留，不用重配。</li>
        <li>验证两件事：设备网页脚注显示 2.2.49；之后再走一次网页 OTA 应能正常升级（OTA 已恢复）。</li>
      </ol>
      <h2>安全禁忌</h2>
      <ul class="art">
        <li>上电时 GPIO0 对 GND 短接是 ESP32 正常的下载模式进入方法，<strong>不会伤芯片</strong>，不用怕。</li>
        <li><strong>绝对避免</strong> 3.3V / 5V 对 GND 短路，以及 5V 进 TX / RX——这两样才是真的会烧东西。</li>
        <li>短接只短 GPIO0 那两个孔，不要碰到旁边的其他焊盘。</li>
      </ul>
      <h2>装上之后</h2>
      <p>2.2.30 起自带“修复 OTA 状态”按钮与升级结果日志：以后 OTA 再卡住，先点修复按钮（只重置 otadata，不动 WiFi 与配对），不要一上来就恢复出厂，更不要反复重刷。</p>
    </div>
  </article>
</div>"""
    open(os.path.join(SITE, "daikin-flash.html"), "w", encoding="utf-8").write(
        page("大金 AB 版串口刷机指南 · 开发日志", "大金 AB 版传感器串口刷机：J2 接线、GPIO0 短接进 BOOT、esptool 刷 2.2.49。", "index.html", guide_body))
    print("daikin guide -> daikin-flash.html")

if __name__ == "__main__":
    build()
    build_guide()
    build_services()
