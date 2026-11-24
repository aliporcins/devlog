#!/usr/bin/env python3
"""Post the daily free-apps list to the Telegram channel @freeapps_daily,
mirroring the blog post: cover image, then ONE message per app — a wide
banner (banner-<id>.jpg, screenshots stitched side by side) with a
structured HTML caption. No blog URL is included anywhere. The category
is shown inside each app's caption (📂 分类：<category>); NO separate
category header messages are sent (user decision 2026-11-24 — bare
headers from a partial run fragmented the channel).

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
    📁 名称：<name>
    📂 分类：<category>
    🍎 平台：<devices> · iOS <min_os>+
    💰 价格：<s>$4.99</s> → <b>0 元</b>
    ⭐ 评分：★4.8 (4,055)
    🌐 语言：中文、英文、日文等 5 种
    📝 简介：<one-line intro>
    📲 下载链接：<a href="...">在 App Store 打开</a>
  IAP apps start with #终身内购. The first line is the IAP name itself
  (🎁 内购：<iap> — it already contains the app name, so there is NO
  separate 名称 line), then 📂 分类, then the IAP price
  (💰 内购价格 — $9.99 is the IAP price, not the app price):
    🎟️ 兑换链接：<a href="...">点这里兑换</a>
  The '📝 解锁内容' line was removed (it only repeated the IAP name);
  '📝 简介' (the app intro, same format as paid posts) takes its place.
  Redeem links are PUBLIC direct Apple links only
  (https://apps.apple.com/redeem?ctx=offercodes&id=<id>&code=<code>) —
  a custom offer code the developer published openly. No AppHunt links
  are ever sent (user rule 2026-11-23). When no public code is known the
  claim line is omitted entirely; the app is still listed with just its
  App Store link.

Rate limits: on HTTP 429 the retry_after value is honored and the failed
send retried (up to 3 times). Sent message IDs are recorded in
automation/data/<date>/posted.json INCREMENTALLY as each message
succeeds. Before posting anything, a getMe pre-flight check fails fast
when Telegram is unreachable. If the run fails midway, it rolls back:
every message posted by THIS run is deleted and posted.json is
reverted to its pre-run state, so the next run re-posts the full set
fresh instead of patching the channel. 4s sleep between sends.
"""
import argparse
import html
import json
import os
import re
import sys
import time
import traceback
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


def preflight(token):
    """Quick Telegram reachability check (getMe) before posting
    anything. A dead connection must fail fast with a clear error and
    post NOTHING — a partial batch is how the channel got fragmented
    (2026-11-23: first real run died mid-post). Returns True when
    Telegram answers."""
    try:
        res = bot_api_retry(token, "getMe", tries=2)
    except Exception as e:
        print(f"pre-flight check failed: cannot reach Telegram ({e}); "
              f"posting nothing", file=sys.stderr)
        return False
    if not res.get("ok"):
        print(f"pre-flight check failed: Telegram returned {res}; "
              f"posting nothing", file=sys.stderr)
        return False
    print(f"pre-flight check ok: Telegram reachable "
          f"(bot @{res['result'].get('username')})")
    return True


def _parse_paid_app(sec):
    """Fields of one paid app section (blog post)."""
    name = sec.split("\n", 1)[0].strip()
    if name.startswith("---") or not name:
        return None
    icon = re.search(r"!\[.*?\]\(\.\./assets/([^)]+)\)", sec)
    orig = re.search(r"\*\*原价\*\*：([^，\n]+)", sec)
    rating = re.search(r"\*\*评分\*\*：★([^\n]+)", sec)
    size = re.search(r"\*\*大小\*\*：([^\n]+)", sec)
    devices = re.search(r"\*\*(?:支持)?设备\*\*：([^\n]+)", sec)
    min_os = re.search(r"\*\*最低系统\*\*：iOS ([^\n]+)", sec)
    desc = re.search(r"\*\*简介\*\*：([^\n]+)", sec)
    link = re.search(r"\[在 App Store 打开\]\(([^)]+)\)", sec)
    return {
        "name": name,
        "icon": icon.group(1) if icon else "",
        "orig": orig.group(1).strip() if orig else "",
        "rating": rating.group(1).strip() if rating else "",
        "size": size.group(1).strip() if size else "",
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
    size = re.search(r"\*\*大小\*\*：([^\n]+)", sec)
    devices = re.search(r"\*\*(?:支持)?设备\*\*：([^\n]+)", sec)
    desc = re.search(r"\*\*简介\*\*：([^\n]+)", sec)
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
        "size": size.group(1).strip() if size else "",
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
    2026-11-23 post (IAP sections also carry 评分/设备/简介).
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


def rating_line(a):
    """⭐ 评分：4.6 — score only, no rating count. The blog stores
    rating as '4.6 (28,711)' (parsed from '★4.6 (28,711)'). No rating,
    or a 0.0 rating, returns '' so the line is omitted — never
    invented."""
    r = str(a.get("rating") or "").strip()
    if not r:
        return ""
    m = re.match(r"([\d.]+)\s*\(([\d,]+)\)", r)
    if not m:
        return ""
    val, count = m.group(1), m.group(2)
    try:
        if float(val) <= 0 or int(count.replace(",", "")) <= 0:
            return ""
    except ValueError:
        return ""
    return f"⭐ 评分：{val}"


def platform_line(a):
    """平台：devices · iOS <min_os>+ (parts omitted when unknown).
    iPod touch is dropped: the product is discontinued and the extra
    segment makes the line wrap mid-phrase on phones. Apple TV-only
    apps say so clearly: "Apple TV · tvOS <min_tvos>+" (the iOS
    minimum does not apply to tvOS); universal apps list Apple TV
    among the devices, e.g. "iPhone / iPad / Apple TV · iOS 17.0+"."""
    parts = []
    if a.get("devices"):
        devs = " / ".join(
            d.strip() for d in a["devices"].split("/") if d.strip() != "iPod touch"
        )
        if devs:
            parts.append(devs)
    if parts and parts[0] == "Apple TV":
        # tvOS-only: the iOS minimum is meaningless here.
        tvos = a.get("min_tvos")
        if tvos and tvos != "?":
            parts.append(f"tvOS {tvos}+")
    elif a.get("min_os"):
        parts.append(f"iOS {a['min_os']}+")
    return " · ".join(parts)


def price_line(orig, free_word, label="价格"):
    """价格：<s>$0.99</s> → <b>0 元</b> (free_word carries the HTML).
    IAP posts pass label="内购价格" — $9.99 is the IAP price, not the
    app price. Only a dollar amount gets struck through: when the
    original price is unknown the blog writes a word instead
    ("付费应用" / "兑换码 0 元领"), and striking that through reads
    as "~~付费应用~~ → 0 元". Unknown price shows just the free word."""
    if orig and orig.startswith("$"):
        return f"💰 {label}：<s>{esc(orig)}</s> → {free_word}"
    return f"💰 {label}：{free_word}"


def paid_caption(a, lang_txt):
    """Paid caption — locked format (2026-11-24): one continuous header
    block (name / price / category / platform / rating / size /
    languages, NO blank lines), then a blank line, the intro paragraph,
    a blank line, and the download link. Price is the hook, right
    after the name. Rating is score only. Platform shows Apple TV
    when supported; iPod touch is dropped."""
    lines = ["#应用限免",
             f"📁 名称：{esc(a['name'])}",
             price_line(a["orig"], "<b>0 元</b>")]
    if a.get("category"):
        lines.append(f"📂 分类：{esc(a['category'])}")
    plat = platform_line(a)
    if plat:
        lines.append(f"📱 平台：{esc(plat)}")
    rl = rating_line(a)
    if rl:
        lines.append(rl)
    if a.get("size"):
        lines.append(f"💾 大小：{esc(a['size'])}")
    if lang_txt:
        lines.append(f"🌐 语言：{esc(lang_txt)}")
    if a.get("desc"):
        lines += ["", f"📝 简介：{esc(a['desc'])}"]
    if a.get("link"):
        lines += ["", f'📲 下载链接：<a href="{a["link"]}">在 App Store 打开</a>']
    return "\n".join(lines)


def iap_caption(a, lang_txt, redeem_url=""):
    """IAP caption — same layout as the live posting script. redeem_url
    is a PUBLIC Apple redeem link (apps.apple.com/redeem?ctx=offercodes
    &id=..&code=..); when empty the claim line is omitted entirely.
    No AppHunt links are ever sent. The '解锁内容' line was removed
    (it only repeated the IAP name); the app intro ('📝 简介',
    from the parsed '简介' field) takes its place, same format as
    paid posts. Lead line (2026-11-24): the APP name, not the IAP
    name — the IAP name is almost always the app name plus a suffix
    (Pro/Premium), so it adds nothing; the app name is what readers
    recognise and search for, and the redeem link already points at
    the exact IAP. The price is labelled 内购价格 (it is the IAP
    price, not the app price). Category is a line inside the caption.
    Same locked header block as paid captions: name / price / category
    / platform / rating / size / languages with NO blank lines; blank
    lines only before the intro and before the links."""
    lines = ["#终身内购",
             f"📁 名称：{esc(a['name'])}",
             price_line(a["orig"], "<b>0 元</b>", label="内购价格")]
    if a.get("left"):
        lines.append(f"📦 剩余兑换码：{esc(a['left'])}")
    if a.get("category"):
        lines.append(f"📂 分类：{esc(a['category'])}")
    plat = platform_line(a)
    if plat:
        lines.append(f"📱 平台：{esc(plat)}")
    rl = rating_line(a)
    if rl:
        lines.append(rl)
    if a.get("size"):
        lines.append(f"💾 大小：{esc(a['size'])}")
    if lang_txt:
        lines.append(f"🌐 语言：{esc(lang_txt)}")
    if a.get("desc"):
        lines += ["", f"📝 简介：{esc(a['desc'])}"]
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
    # No fallback: when the post has no recommendation section (no
    # Chinese app that day), featured stays empty and the cover caption
    # carries no recommendation line either — English-only apps must
    # not be promoted into the featured slot here.

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
    # Snapshot of the pre-run state + the message ids THIS run posts.
    # Rollback (below) deletes exactly these ids and reverts posted.json
    # to this snapshot, so a failed run leaves the channel clean and
    # the next run re-posts the full set fresh instead of patching.
    posted_before = dict(posted)
    this_run_ids = []

    def record(key, message_ids):
        posted[key] = message_ids
        this_run_ids.extend(message_ids)
        with open(posted_path, "w") as f:
            json.dump(posted, f, indent=1)

    def rollback():
        """Best-effort rollback: delete every message posted by THIS
        run and revert posted.json to its pre-run state. Never raises
        — a failed rollback must not mask the original error, and it
        must never touch messages from earlier runs (they are not in
        this_run_ids)."""
        if not this_run_ids:
            return
        print(f"[rollback] deleting {len(this_run_ids)} message(s) "
              f"posted by this run...")
        if token:
            for mid in this_run_ids:
                try:
                    res = bot_api_retry(token, "deleteMessage",
                                        {"chat_id": str(chat_id),
                                         "message_id": mid}, tries=2)
                    print(f"  [rollback] delete {mid}: {res.get('ok')}")
                except Exception as e:
                    print(f"  [rollback] delete {mid} failed "
                          f"(ignored): {e}")
        try:
            with open(posted_path, "w") as f:
                json.dump(posted_before, f, indent=1)
            print("[rollback] posted.json reverted to pre-run state")
        except Exception as e:
            print(f"[rollback] could not revert posted.json "
                  f"(ignored): {e}")

    def fail(msg):
        """Log the failure, roll back this run's posts, return 1."""
        print(msg, file=sys.stderr)
        rollback()
        return 1

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

    # Pre-flight: fail fast when Telegram is unreachable, BEFORE
    # posting anything. A dead connection mid-run is what left a
    # partial batch in the channel (2026-11-23). Skipped in dry-run
    # (no token, nothing is sent).
    if not args.dry_run and not preflight(token):
        return fail("pre-flight check failed: Telegram unreachable, "
                    "posting nothing")

    try:
        rc = _post_all(args, token, chat_id, date, date_cn, sleep_s,
                       featured, paid_apps, iap_apps, langs, posted,
                       record, fail, photo_for)
    except Exception:
        traceback.print_exc()
        return fail("unexpected error during posting (rolled back)")
    return rc


def _post_all(args, token, chat_id, date, date_cn, sleep_s,
              featured, paid_apps, iap_apps, langs, posted,
              record, fail, photo_for):
    """The three posting steps (cover, paid apps, IAPs). Separated so
    main() can wrap it in try/except and roll back on any crash.
    Failure paths return fail(...) (which rolls back and returns 1);
    the caller propagates that return value."""
    # 1. Cover photo + intro caption
    if not args.only and "cover" not in posted:
        cover = os.path.join(
            ROOT, "assets", f"free-apps-{date.replace('-', '')}", "cover.jpg")
        caption = "📱 <b>今日限免（{date_cn}）</b>\n\n".format(date_cn=date_cn)
        if featured:
            caption += ("⭐ <b>今日极力推荐</b>："
                        f"{'、'.join(featured)}\n\n")
        caption += (f"今日 {len(paid_apps)} 款完全免费（不含内购）＋ "
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
                return fail(f"cover failed: {res}")
            record("cover", [res["result"]["message_id"]])
        time.sleep(sleep_s)

    # 2. One banner photo per paid app. The category is shown inside
    # each app's caption (📂 分类：...); no separate header messages.
    if args.only in (None, "apps"):
        for a in paid_apps:
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
                return fail(f"app {a['name']} failed: {res}")
            record(key, [res["result"]["message_id"]])
            time.sleep(sleep_s)

    # 3. IAPs: intro + one banner photo per IAP. Category is inside
    # each IAP's caption; no separate header messages.
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
                    return fail(f"iap intro failed: {res}")
                record("iap_intro", [res["result"]["message_id"]])
            time.sleep(sleep_s)
        for a in iap_apps:
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
                return fail(f"iap {a['name']} failed: {res}")
            record(key, [res["result"]["message_id"]])
            time.sleep(sleep_s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
