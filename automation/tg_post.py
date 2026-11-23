#!/usr/bin/env python3
"""Post the daily free-apps list to the Telegram channel @freeapps_daily,
mirroring the blog post: cover image, then ONE message per app — a wide
banner (banner-<id>.jpg, screenshots stitched side by side) with a
structured HTML caption. No blog URL is included anywhere. Apps are
grouped by category (the blog post's category sub-headings): a short
category header message (📂 <category>（N 款/个）) opens each group,
recorded in posted.json so a re-run does not repeat it.

Usage:
  tg_post.py --date 2026-11-23 [--only apps|iap] [--dry-run]

Reads the blog post posts/<date>-free-apps.md and
automation/data/<date>/languages.json. Bot token comes from
TELEGRAM_BOT_TOKEN (or ~/workspace/telegram-freeapps-bot/config.json for
local runs); channel id from TG_CHANNEL_ID or the constant below.

Caption format (structured fields, HTML — same layout as the live
posting script tg_channel_post_full.py):
  Paid apps start with #应用限免:
    #应用限免
    📁 软件名称：<name>
    🍎 支持平台：<devices> · iOS <min_os>+
    💰 软件价格：<s>$4.99</s> → <b>免费</b>
    ⭐ 评分：★4.8 (4,055)
    🌐 支持语言：中文、英文、日文等 5 种
    📝 软件简介：<one-line intro>
    📲 下载链接：<a href="...">在 App Store 打开</a>
  IAP apps start with #终身内购 and additionally carry 内购 / 剩余兑换码 /
  软件简介， and end with the public redeem link when one is known:
    🎟️ 兑换链接：<a href="...">点这里兑换</a>
  The '📝 解锁内容' line was removed (it only repeated the IAP name);
  '📝 软件简介' (the app intro, same format as paid posts) takes its place.
  Redeem links are PUBLIC direct Apple links only
  (https://apps.apple.com/redeem?ctx=offercodes&id=<id>&code=<code>) —
  a custom offer code the developer published openly. No AppHunt links
  are ever sent (user rule 2026-11-23). When no public code is known the
  claim line is omitted entirely; the app is still listed with just its
  App Store link.

Rate limits: on HTTP 429 the retry_after value is honored and the failed
send retried (up to 3 times). Sent message IDs are recorded in
automation/data/<date>/posted.json; a re-run skips apps already posted
(resume), so a 429 never causes duplicates. 4s sleep between sends.
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.expanduser("~/workspace/telegram-freeapps-bot/config.json")
CHANNEL_ID = os.environ.get("TG_CHANNEL_ID", "-1004423043910")

LANG_NAMES = {
    "AR": "阿拉伯文", "BN": "孟加拉文", "CA": "加泰罗尼亚文", "HR": "克罗地亚文",
    "CS": "捷克文", "DA": "丹麦文", "NL": "荷兰文", "EN": "英文", "FI": "芬兰文",
    "FR": "法文", "DE": "德文", "EL": "希腊文", "GU": "古吉拉特文", "HE": "希伯来文",
    "HI": "印地文", "HU": "匈牙利文", "ID": "印尼文", "IT": "意大利文", "JA": "日文",
    "KN": "卡纳达文", "KO": "韩文", "MS": "马来文", "ML": "马拉雅拉姆文", "MR": "马拉地文",
    "NB": "挪威文", "OR": "奥里亚文", "PL": "波兰文", "PT": "葡萄牙文", "PA": "旁遮普文",
    "RO": "罗马尼亚文", "RU": "俄文", "ZH": "中文", "SK": "斯洛伐克文", "SL": "斯洛文尼亚文",
    "ES": "西班牙文", "SV": "瑞典文", "TA": "泰米尔文", "TE": "泰卢固文", "TH": "泰文",
    "TR": "土耳其文", "UK": "乌克兰文", "UR": "乌尔都文", "VI": "越南文",
}
LANG_PRIORITY = ["ZH", "EN", "JA", "KO", "FR", "DE", "ES", "PT", "RU", "IT"]


def format_langs(codes):
    """Compact language display, e.g. '中文、英文、日文等 32 种' or '仅英文'."""
    seen = []
    for c in codes or []:
        if c not in seen:
            seen.append(c)
    if not seen:
        return ""
    if len(seen) == 1 and seen[0] == "EN":
        return "仅英文"
    ordered = [c for c in LANG_PRIORITY if c in seen]
    rest = [c for c in seen if c not in LANG_PRIORITY]
    ordered += rest
    names = [LANG_NAMES.get(c, c) for c in ordered]
    if len(names) <= 5:
        return "、".join(names)
    return "、".join(names[:5]) + f"等 {len(names)} 种"


def get_token():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        return token
    with open(CONFIG) as f:
        return json.load(f)["bot_token"]


def bot_api(token, method, payload=None, files=None):
    """One Bot API call. Returns the parsed JSON (ok False on API error).
    Raises HTTPError only for transport errors; 429 is surfaced to caller."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    if files:
        boundary = "----" + uuid.uuid4().hex
        body = b""
        for k, v in (payload or {}).items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
            body += f"{v}\r\n".encode()
        for field, path, fname in files:
            with open(path, "rb") as f:
                data = f.read()
            body += f"--{boundary}\r\n".encode()
            body += (f'Content-Disposition: form-data; name="{field}"; '
                     f'filename="{fname}"\r\n').encode()
            body += b"Content-Type: image/jpeg\r\n\r\n"
            body += data + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    else:
        data = json.dumps(payload or {}).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def bot_api_retry(token, method, payload=None, files=None, tries=3):
    """bot_api with 429 handling and transient-network retry. A single
    'Connection reset by peer' / timeout must not kill the whole run:
    Telegram's API (and the runner's egress) occasionally drops a
    connection, so URLError is retried with backoff; only after all
    attempts fail does it return ok=False (callers then fail cleanly
    instead of crashing with a traceback)."""
    for attempt in range(tries):
        try:
            res = bot_api(token, method, payload, files)
            if res.get("ok"):
                return res
            # API-level error (e.g. 429 surfaced as JSON)
            if res.get("error_code") == 429:
                wait = res.get("parameters", {}).get("retry_after", 60)
                print(f"  429, waiting {wait}s (attempt {attempt + 1})")
                time.sleep(wait + 2)
                continue
            return res
        except urllib.error.HTTPError as e:
            if e.code == 429:
                try:
                    body = json.loads(e.read().decode())
                    wait = body.get("parameters", {}).get("retry_after", 60)
                except Exception:
                    wait = 60
                print(f"  HTTP 429, waiting {wait}s (attempt {attempt + 1})")
                time.sleep(wait + 2)
                continue
            raise
        except urllib.error.URLError as e:
            # Transient network error (connection reset, timeout, DNS).
            print(f"  network error {e} (attempt {attempt + 1})")
            if attempt + 1 < tries:
                time.sleep(5 * (attempt + 1))
                continue
            return {"ok": False, "error": f"network error: {e}"}
    return {"ok": False, "error": "retries exhausted"}


def _parse_paid_app(sec):
    """Fields of one paid app section (blog post)."""
    name = sec.split("\n", 1)[0].strip()
    if name.startswith("---") or not name:
        return None
    icon = re.search(r"!\[.*?\]\(\.\./assets/([^)]+)\)", sec)
    orig = re.search(r"\*\*原价\*\*：([^，\n]+)", sec)
    rating = re.search(r"\*\*评分\*\*：★([^\n]+)", sec)
    devices = re.search(r"\*\*支持设备\*\*：([^\n]+)", sec)
    min_os = re.search(r"\*\*最低系统\*\*：iOS ([^\n]+)", sec)
    desc = re.search(r"\*\*干什么的\*\*：([^\n]+)", sec)
    link = re.search(r"\[在 App Store 打开\]\(([^)]+)\)", sec)
    return {
        "name": name,
        "icon": icon.group(1) if icon else "",
        "orig": orig.group(1).strip() if orig else "",
        "rating": rating.group(1).strip() if rating else "",
        "devices": devices.group(1).strip() if devices else "",
        "min_os": min_os.group(1).strip() if min_os else "",
        "desc": desc.group(1).strip() if desc else "",
        "link": link.group(1) if link else "",
    }


def _parse_iap_app(sec):
    """Fields of one IAP promo section (blog post)."""
    name = sec.split("\n", 1)[0].strip()
    if name.startswith("---") or not name:
        return None
    icon = re.search(r"!\[.*?\]\(\.\./assets/([^)]+)\)", sec)
    iap = re.search(r"\*\*内购\*\*：([^\n]+)", sec)
    orig = re.search(r"\*\*原价\*\*：([^，\n]+)", sec)
    rating = re.search(r"\*\*评分\*\*：★([^\n]+)", sec)
    devices = re.search(r"\*\*支持设备\*\*：([^\n]+)", sec)
    desc = re.search(r"\*\*干什么的\*\*：([^\n]+)", sec)
    unlock = re.search(r"\*\*解锁内容\*\*：([^\n]+)", sec)
    left = re.search(r"\*\*剩余兑换码\*\*：([^\n]+)", sec)
    min_os = re.search(r"\*\*最低系统\*\*：iOS ([^\n]+)", sec)
    link = re.search(r"\[在 App Store 打开\]\(([^)]+)\)", sec)
    redeem = re.search(
        r"https://apps\.apple\.com/redeem\?[^)\s\"']+", sec)
    return {
        "name": name,
        "icon": icon.group(1) if icon else "",
        "iap": iap.group(1).strip() if iap else "",
        "orig": orig.group(1).strip() if orig else "",
        "rating": rating.group(1).strip() if rating else "",
        "devices": devices.group(1).strip() if devices else "",
        "desc": desc.group(1).strip() if desc else "",
        "unlock": unlock.group(1).strip() if unlock else "",
        "left": left.group(1).strip() if left else "",
        "min_os": min_os.group(1).strip() if min_os else "",
        "link": link.group(1) if link else "",
        "redeem": redeem.group(0) if redeem else "",
    }


def _parse_section_apps(sec_text, is_iap):
    """Parse one section (paid or IAP) into app dicts with 'category'.

    Grouped format (2+ categories): `### <Category>（N 款/个）` headings
    with `#### N. Name` apps underneath. Flat format (one category):
    `### N. Name` apps directly. Both are accepted so an older flat
    post still parses."""
    parse_one = _parse_iap_app if is_iap else _parse_paid_app
    apps = []
    # Grouped: split on category headings (capture group keeps the name).
    parts = re.split(r"\n### ([^#\n]+?)（\d+ [款个]）\n", sec_text)
    if len(parts) >= 3:
        for j in range(1, len(parts), 2):
            cat = parts[j].strip()
            for sec in re.split(r"\n#### \d+\. ", parts[j + 1])[1:]:
                a = parse_one(sec)
                if a:
                    a["category"] = cat
                    apps.append(a)
        return apps
    for sec in re.split(r"\n### \d+\. ", sec_text)[1:]:
        a = parse_one(sec)
        if a:
            a["category"] = ""
            apps.append(a)
    return apps


def parse_post(md):
    """Return (featured_names, paid_apps, iap_apps) — same format as the
    2026-11-23 post (IAP sections also carry 评分/支持设备/干什么的).
    Each app dict also carries 'category' ('' when the post is flat)."""
    featured = []
    m = re.search(r"## 今日极力推荐(.*?)(?=\n## |\Z)", md, re.S)
    if m:
        featured = [x.strip() for x in
                    re.findall(r"\d+\.\s*([^\n]+)", m.group(1))]
    paid_sec = re.search(r"## 付费应用限时免费.*?(?=\n## 终身内购|\Z)", md, re.S)
    iap_sec = re.search(r"## 终身内购.*", md, re.S)
    paid_apps = _parse_section_apps(paid_sec.group(0), False) if paid_sec else []
    iap_apps = _parse_section_apps(iap_sec.group(0), True) if iap_sec else []
    return featured, paid_apps, iap_apps


def esc(s):
    return html.escape(s or "")


def platform_line(a):
    """支持平台：devices · iOS <min_os>+ (parts omitted when unknown)."""
    parts = []
    if a.get("devices"):
        parts.append(a["devices"])
    if a.get("min_os"):
        parts.append(f"iOS {a['min_os']}+")
    return " · ".join(parts)


def price_line(orig, free_word):
    """软件价格：<s>$4.99</s> → <b>免费</b> (free_word carries the HTML)."""
    if orig:
        return f"💰 软件价格：<s>{esc(orig)}</s> → {free_word}"
    return f"💰 软件价格：{free_word}"


def paid_caption(a, lang_txt):
    """Paid caption — same layout as the live posting script."""
    lines = ["#应用限免", "",
             f"📁 软件名称：{esc(a['name'])}"]
    plat = platform_line(a)
    if plat:
        lines.append(f"🍎 支持平台：{esc(plat)}")
    lines.append(price_line(a["orig"], "<b>免费</b>"))
    if a.get("rating") and not a["rating"].startswith("0.0"):
        lines.append(f"⭐ 评分：★{esc(a['rating'])}")
    if lang_txt:
        lines.append(f"🌐 支持语言：{esc(lang_txt)}")
    if a.get("desc"):
        lines += ["", f"📝 软件简介：{esc(a['desc'])}"]
    if a.get("link"):
        lines += ["", f'📲 下载链接：<a href="{a["link"]}">在 App Store 打开</a>']
    return "\n".join(lines)


def iap_caption(a, lang_txt, redeem_url=""):
    """IAP caption — same layout as the live posting script. redeem_url
    is a PUBLIC Apple redeem link (apps.apple.com/redeem?ctx=offercodes
    &id=..&code=..); when empty the claim line is omitted entirely.
    No AppHunt links are ever sent. The '解锁内容' line was removed
    (it only repeated the IAP name); the app intro ('📝 软件简介',
    from the parsed '干什么的' field) takes its place, same format as
    paid posts."""
    lines = ["#终身内购", "",
             f"📁 软件名称：{esc(a['name'])}"]
    if a.get("iap"):
        lines.append(f"🎁 内购：{esc(a['iap'])}")
    plat = platform_line(a)
    if plat:
        lines.append(f"🍎 支持平台：{esc(plat)}")
    lines.append(price_line(a["orig"], "<b>0 元</b>"))
    if a.get("left"):
        lines.append(f"📦 剩余兑换码：{esc(a['left'])}")
    if lang_txt:
        lines.append(f"🌐 支持语言：{esc(lang_txt)}")
    if a.get("desc"):
        lines += ["", f"📝 软件简介：{esc(a['desc'])}"]
    if a.get("link"):
        lines += ["", f'📲 下载链接：<a href="{a["link"]}">在 App Store 打开</a>']
    if redeem_url:
        lines.append(f'🎟️ 兑换链接：<a href="{redeem_url}">点这里兑换</a>')
    return "\n".join(lines)


def app_id_of(a):
    m = re.search(r"id(\d+)", a.get("link") or "")
    return m.group(1) if m else ""


def banner_path(date, app_id):
    """assets/free-apps-<date>/banner-<appid>.jpg"""
    return os.path.join(ROOT, "assets", f"free-apps-{date.replace('-', '')}",
                        f"banner-{app_id}.jpg")


def send_photo(token, chat_id, photo_path, caption):
    return bot_api_retry(token, "sendPhoto",
                         {"chat_id": str(chat_id), "caption": caption,
                          "parse_mode": "HTML"},
                         files=[("photo", photo_path, "banner.jpg")])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--only", choices=["apps", "iap"], default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="print captions instead of sending")
    args = ap.parse_args()
    date = args.date
    token = None if args.dry_run else get_token()
    chat_id = CHANNEL_ID

    md_path = os.path.join(ROOT, "posts", f"{date}-free-apps.md")
    with open(md_path) as f:
        md = f.read()
    featured, paid_apps, iap_apps = parse_post(md)
    if not featured and paid_apps:
        featured = [a["name"] for a in paid_apps[:3]]

    lang_path = os.path.join(ROOT, "automation", "data", date, "languages.json")
    langs = {}
    if os.path.isfile(lang_path):
        with open(lang_path) as f:
            langs = json.load(f)

    posted_path = os.path.join(ROOT, "automation", "data", date, "posted.json")
    posted = {}
    if os.path.isfile(posted_path):
        with open(posted_path) as f:
            posted = json.load(f)

    def record(key, message_ids):
        posted[key] = message_ids
        with open(posted_path, "w") as f:
            json.dump(posted, f, indent=1)

    def send_category_header(cat, count, unit, key_prefix):
        """One short text message as the sub-heading for a category
        group (e.g. 📂 效率工具（3 款）). Sent once per category; a
        re-run skips it via posted.json. Returns False on failure."""
        key = f"{key_prefix}:{cat}"
        if key in posted:
            return True
        text = f"📂 <b>{esc(cat)}</b>（{count} {unit}）"
        if args.dry_run:
            print(f"[dry-run] category header: {text!r}")
            return True
        res = bot_api_retry(token, "sendMessage",
                            {"chat_id": str(chat_id), "text": text,
                             "parse_mode": "HTML",
                             "disable_web_page_preview": True})
        print(f"category {cat}: {res.get('ok')}")
        if not res.get("ok"):
            print("  failed:", res, file=sys.stderr)
            return False
        record(key, [res["result"]["message_id"]])
        time.sleep(sleep_s)
        return True

    y, m, d = date.split("-")
    date_cn = f"{int(y)}年{int(m)}月{int(d)}日"
    sleep_s = 0 if args.dry_run else 4

    def photo_for(a):
        """Banner first; build it from the screenshots when missing;
        fall back to the app icon if no screenshots are available."""
        app_id = app_id_of(a)
        if app_id:
            b = banner_path(date, app_id)
            if os.path.isfile(b):
                return b
            # Build the banner on demand from the downloaded screenshots
            # (same as the live posting script's banner_for).
            try:
                from banner import build_banner, find_shots
                asset_dir = os.path.join(
                    ROOT, "assets", f"free-apps-{date.replace('-', '')}")
                shots = find_shots(asset_dir, app_id)
                if shots:
                    build_banner(shots, b)
                    return b
            except Exception as e:
                print(f"  banner build failed for {a.get('name')}: {e}")
        if a.get("icon"):
            p = os.path.join(ROOT, "assets", a["icon"])
            if os.path.isfile(p):
                return p
        return ""

    # 1. Cover photo + intro caption
    if not args.only and "cover" not in posted:
        cover = os.path.join(
            ROOT, "assets", f"free-apps-{date.replace('-', '')}", "cover.jpg")
        feat_txt = "、".join(featured)
        caption = (f"📱 <b>今日限免（{date_cn}）</b>\n\n"
                   f"⭐ <b>今日极力推荐</b>：{feat_txt}\n\n"
                   f"今日 {len(paid_apps)} 款完全免费（不含内购）＋ "
                   f"{len(iap_apps)} 个终身内购 0 元兑换\n"
                   f"⏰ 限免随时结束，看到喜欢的尽快领。")
        if args.dry_run:
            print(f"[dry-run] cover: {caption!r}")
            print(f"[dry-run] cover file exists: {os.path.isfile(cover)}")
        else:
            res = bot_api_retry(token, "sendPhoto",
                                {"chat_id": str(chat_id), "caption": caption,
                                 "parse_mode": "HTML"},
                                files=[("photo", cover, "cover.jpg")])
            print("cover:", res.get("ok"),
                  res.get("result", {}).get("message_id"))
            if not res.get("ok"):
                print("cover failed:", res, file=sys.stderr)
                return 1
            record("cover", [res["result"]["message_id"]])
        time.sleep(sleep_s)

    # 2. One banner photo per paid app, grouped by category: a short
    # category header message opens each group.
    if args.only in (None, "apps"):
        paid_cat_counts = {}
        for a in paid_apps:
            c = a.get("category", "")
            if c:
                paid_cat_counts[c] = paid_cat_counts.get(c, 0) + 1
        cur_cat = None
        for a in paid_apps:
            cat = a.get("category", "")
            if cat and cat != cur_cat:
                if not send_category_header(cat, paid_cat_counts.get(cat, 0),
                                            "款", "cat"):
                    return 1
                cur_cat = cat
            key = f"app:{a['link']}"
            if key in posted:
                print(f"app {a['name']}: already posted, skipped")
                continue
            photo = photo_for(a)
            if not photo:
                print(f"app {a['name']}: no image, skipped")
                continue
            lang_txt = format_langs(langs.get(app_id_of(a), []))
            cap = paid_caption(a, lang_txt)
            if args.dry_run:
                print(f"[dry-run] app {a['name']}: photo={photo}")
                print(f"[dry-run] caption:\n{cap}")
                print(f"[dry-run] blog url in caption: "
                      f"{'devlog' in cap or 'pages.dev' in cap}")
                continue
            res = send_photo(token, chat_id, photo, cap)
            ok = res.get("ok")
            print(f"app {a['name']}: {ok}")
            if not ok:
                print("  failed:", res, file=sys.stderr)
                return 1
            record(key, [res["result"]["message_id"]])
            time.sleep(sleep_s)

    # 3. IAPs: intro + one banner photo per IAP
    if args.only in (None, "iap") and iap_apps:
        if "iap_intro" not in posted:
            text = ("<b>终身内购 0 元兑换</b>\n\n"
                    "开发者发的兑换码，点帖子里的兑换链接直接进 App Store 兑。"
                    "每个码一个账号只能用一次，终身解锁、不续费。")
            if args.dry_run:
                print(f"[dry-run] iap intro: {text!r}")
            else:
                res = bot_api_retry(token, "sendMessage",
                                    {"chat_id": str(chat_id), "text": text,
                                     "parse_mode": "HTML",
                                     "disable_web_page_preview": True})
                print("iap intro:", res.get("ok"))
                if not res.get("ok"):
                    print("  failed:", res, file=sys.stderr)
                    return 1
                record("iap_intro", [res["result"]["message_id"]])
            time.sleep(sleep_s)
        iap_cat_counts = {}
        for a in iap_apps:
            c = a.get("category", "")
            if c:
                iap_cat_counts[c] = iap_cat_counts.get(c, 0) + 1
        cur_cat = None
        for a in iap_apps:
            cat = a.get("category", "")
            if cat and cat != cur_cat:
                if not send_category_header(cat, iap_cat_counts.get(cat, 0),
                                            "个", "iapcat"):
                    return 1
                cur_cat = cat
            key = f"iap:{a['link']}"
            if key in posted:
                print(f"iap {a['name']}: already posted, skipped")
                continue
            photo = photo_for(a)
            if not photo:
                print(f"iap {a['name']}: no image, skipped")
                continue
            lang_txt = format_langs(langs.get(app_id_of(a), []))
            cap = iap_caption(a, lang_txt, a.get("redeem", ""))
            if args.dry_run:
                print(f"[dry-run] iap {a['name']}: photo={photo} "
                      f"redeem={a.get('redeem') or '(none)'}")
                print(f"[dry-run] caption:\n{cap}")
                print(f"[dry-run] blog url in caption: "
                      f"{'devlog' in cap or 'pages.dev' in cap}")
                continue
            res = send_photo(token, chat_id, photo, cap)
            ok = res.get("ok")
            print(f"iap {a['name']}: {ok}")
            if not ok:
                print("  failed:", res, file=sys.stderr)
                return 1
            record(key, [res["result"]["message_id"]])
            time.sleep(sleep_s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
