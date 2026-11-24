#!/usr/bin/env python3
"""Daily iOS free-apps pipeline: scrape -> verify -> blog post -> deploy -> Telegram.

Usage:
  python3 pipeline.py [--date YYYY-MM-DD] [--dry-run] [--skip-deploy] [--skip-telegram]

- Scrapes Mergeek / GoFans / AppRaven / 360-reader for paid-turned-free apps
  and oodata.net + a curated list for lifetime IAPs with PUBLIC Apple
  redeem links (apps.apple.com/redeem?ctx=offercodes&id=..&code=..).
  AppHunt is used only to discover which apps have a free lifetime IAP;
  no AppHunt links, codes, or code counts are ever published. An IAP with
  no public code is listed with just its App Store link.
- Verifies every paid app is currently free (iTunes Lookup, price 0, US) and
  has NO in-app purchases (App Store page <dt>In-App Purchases</dt> check;
  iTunes Lookup has no IAP field). It also cross-checks each kept paid
  app against the AppRaven FREE list (the website's public GetAppsOnSale,
  no login, no Pro): apps that went free in the last 48h and that no other
  source caught are added as candidates, and each kept app's price history
  (GetAppDetail activityList) is verified — an app that launched free and
  was never paid is dropped as a perennially-free false positive. A
  missing/inconclusive AppRaven record never blocks an app (fail-open);
  the counts are logged as [appraven-xcheck].
- Apps are grouped by App Store category (primaryGenreName mapped to a
  Chinese name, e.g. Productivity -> 效率工具) in the blog post, the
  Telegram channel, the WeChat article and the Xiaohongshu note. A lone
  category is rendered as a flat list (no forced grouping).
- Writes the blog post (posts/<date>-free-apps.md), downloads icons +
  up to 4 screenshots per app (first 2 in the blog carousel, all stitched
  into a wide channel banner banner-<id>.jpg), writes languages.json +
  apps.json, builds a PIL cover from the featured icons, runs build.py,
  deploys via wrangler (needs CLOUDFLARE_API_TOKEN env), then posts to
  Telegram via tg_post.py.
- App intros are Chinese: the China App Store description is preferred;
  otherwise the English first sentence is machine-translated (three-level
  chain: Google gtx -> dict-chrome-ex -> MyMemory, all free, no API key).
  The raw iTunes record (English description) in apps.json is never modified.
- Also writes automation/data/<date>/wechat.md (a copy-paste-ready WeChat
  Official Account article), automation/data/<date>/wechat.html (the same
  article as standalone HTML with inline styles, for paste into the WeChat
  editor; images are absolute raw-GitHub URLs because the blog itself is
  login-gated) and automation/data/<date>/xiaohongshu.txt
  (a Xiaohongshu note: hook title, one-line Chinese intros, hashtags, no
  external links — readers are told to search the app name in the App
  Store). All are committed with the daily run; deploy and Telegram
  are untouched by them.
- --dry-run: generate everything but skip deploy and Telegram (writes files
  under a test date directory; safe to run any time).
- Never invents a free-app end date; never logs in to Apple ID; never buys.

Repo root is the parent of this script's directory (the devlog checkout).
"""
import argparse
import datetime
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scrape as sc
from banner import build_banner
from tg_post import format_langs
import redeem_codes as rc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTOMATION = os.path.join(ROOT, "automation")
DATA_DIR = os.path.join(AUTOMATION, "data")
POSTS_DIR = os.path.join(ROOT, "posts")
ASSETS_DIR = os.path.join(ROOT, "assets")

UA = sc.UA
USD_TIERS = [0.99, 1.99, 2.99, 3.99, 4.99, 5.99, 6.99, 7.99, 8.99, 9.99,
             11.99, 12.99, 14.99, 17.99, 19.99, 24.99, 29.99, 39.99, 49.99,
             59.99, 69.99, 79.99, 89.99, 99.99]
CNY_USD = 7.1  # rough rate for converting Mergeek/GoFans CNY prices to USD


def cny_to_usd(cny):
    """Snap a CNY price to the nearest standard USD App Store tier."""
    usd = cny / CNY_USD
    return min(USD_TIERS, key=lambda t: abs(t - usd))


# ---------------- iTunes ----------------

def lookup(app_id, country="US"):
    """iTunes Lookup for one app; returns the record dict or None."""
    url = (f"https://itunes.apple.com/lookup?id={app_id}&country={country}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode())
    except Exception as e:
        print(f"  [lookup] {app_id} ({country}) failed: {e}")
        return None
    if d.get("resultCount", 0) == 0:
        return None
    return d["results"][0]


_store_page_cache = {}


def store_page(app_id):
    """Fetch the US App Store page HTML (follows the slug redirect).
    Cached per run: has_iap / iap_list / appletv_min_os all read the
    same page, so one app costs one fetch."""
    if app_id in _store_page_cache:
        return _store_page_cache[app_id]
    url = f"https://apps.apple.com/us/app/id{app_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept-Language": "en-US"})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  [store] {app_id} page failed: {e}")
        html = ""
    _store_page_cache[app_id] = html
    return html


def appletv_min_os(app_id):
    """tvOS minimum version (e.g. "18.5") if the App Store page's
    Compatibility section lists Apple TV, else None.

    The iOS lookup record's supportedDevices never includes tvOS
    (verified: Infuse/Plex list 130+ iOS devices, 0 TV entries), so
    the store page is the only reliable source. None also covers a
    failed page fetch (unknown, not "no tvOS" — callers just don't
    add Apple TV in that case)."""
    html = store_page(app_id)
    if not html:
        return None
    m = re.search(r"Compatibility</dt>(.*?)</details>", html, re.S)
    if not m:
        return None
    sec = m.group(1)
    if "<strong>Apple TV</strong>" not in sec:
        return None
    v = re.search(r"Apple TV</strong>.*?Requires tvOS ([\d.]+) or later",
                  sec, re.S)
    return v.group(1) if v else "?"


def has_iap(app_id):
    """True if the App Store page lists in-app purchases.

    Uses the <dt>In-App Purchases</dt> marker. A bare 'In-App Purchases'
    substring is unreliable (appears in descriptions/footers).
    """
    html = store_page(app_id)
    if not html:
        return None  # unknown; caller decides (treated as has-IAP = skip)
    return bool(re.search(r"<dt[^>]*>In-App Purchases</dt>", html))


def iap_list(app_id):
    """[(name, price)] of in-app purchases from the App Store page."""
    html = store_page(app_id)
    if not html:
        return []
    m = re.search(r"In-App Purchases</dt>(.*?)</details>", html, re.S)
    if not m:
        return []
    out = []
    for name, price in re.findall(
            r"<span>([^<]{1,80})</span>\s*<span>\$([\d.]+)</span>", m.group(1)):
        out.append((name.strip(), float(price)))
    return out


# ---------------- enrichment ----------------

DEVICE_MAP = [("iPhone", "iPhone"), ("iPad", "iPad"),
              ("Mac", "Mac"), ("Watch", "Apple Watch"),
              ("AppleTV", "Apple TV")]
# iPod touch is intentionally absent: discontinued product; the extra
# segment makes the platform line wrap mid-phrase on phones.
DEVICE_ORDER = ["iPhone", "iPad", "Mac", "Apple TV",
                "Apple Watch"]


def format_devices(record):
    seen = []
    for d in record.get("supportedDevices", []):
        for prefix, label in DEVICE_MAP:
            if d.startswith(prefix) and label not in seen:
                seen.append(label)
    # canonical order (matches the live posting script's devices_for)
    return " / ".join([x for x in DEVICE_ORDER if x in seen]) if seen else ""


def format_size(nbytes):
    """Human-readable app size from fileSizeBytes (str or int, may be
    missing): '123.4 MB', '1.2 GB' at >= 1 GiB, '456 KB' below 1 MiB.
    Returns '' when unknown so callers can omit the line."""
    try:
        n = int(nbytes)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.1f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024:.1f} KB"


def devices_for_app(record, app_id):
    """format_devices + Apple TV from the store page (see
    appletv_min_os). All supported devices are listed except iPod
    touch (discontinued, dropped at the source so the blog and the
    TG caption agree). Returns (devices_str, min_tvos_or_None)."""
    devs = format_devices(record)
    tvos = appletv_min_os(app_id)
    if tvos is not None:
        parts = [p.strip() for p in devs.split("/") if p.strip()]
        if "Apple TV" not in parts:
            parts.append("Apple TV")
            devs = " / ".join([x for x in DEVICE_ORDER if x in parts])
    return devs, tvos


# ---------------- categories ----------------
# App Store primaryGenreName -> Chinese category name. Unlisted genres
# fall through to the English original. Used to group the paid / IAP
# lists in the blog post, the Telegram channel, the WeChat article
# (Markdown + HTML) and the Xiaohongshu note.
GENRE_ZH = {
    "Productivity": "效率工具",
    "Games": "游戏",
    "Photo & Video": "摄影与录像",
    "Health & Fitness": "健康健美",
    "Education": "教育",
    "Utilities": "工具",
    "Entertainment": "娱乐",
    "Music": "音乐",
    "Lifestyle": "生活",
    "Finance": "财务",
    "Sports": "体育",
    "News": "新闻",
    "Reference": "参考",
    "Travel": "旅行",
    "Weather": "天气",
    "Business": "商务",
    "Medical": "医疗",
    "Food & Drink": "美食佳饮",
    "Shopping": "购物",
    "Social Networking": "社交",
    "Navigation": "导航",
    "Books": "图书",
    "Magazines & Newspapers": "杂志报刊",
    "Catalogs": "商品目录",
    "Developer Tools": "开发者工具",
    "Graphics & Design": "图形设计",
}


def category_zh(genre_en):
    """Chinese category name for an App Store primaryGenreName."""
    if not genre_en:
        return ""
    return GENRE_ZH.get(genre_en, genre_en)


def group_by_category(apps):
    """Group apps by their Chinese category.

    Returns [(category, [apps]), ...] in first-appearance order (the
    input list is price-sorted, so a category surfaces at the position
    of its priciest app). Apps inside a group keep input order.
    Returns [] when the input is empty, and a single group when every
    app shares one category — the callers decide whether to render
    groups or a flat list (a lone category is rendered flat)."""
    groups = {}
    order = []
    for a in apps:
        cat = a.get("category") or ""
        if cat not in groups:
            groups[cat] = []
            order.append(cat)
        groups[cat].append(a)
    return [(c, groups[c]) for c in order]


_PROMO_WORDS = ("limited time", "get it now", "download now",
                 "celebrat", "free for a limited")
_PROMO_PCT_OFF = re.compile(r"^\s*\d+\s*%\s*off\b", re.I)
_PROMO_FREE_ALONE = re.compile(r"^free[!.\s]*$", re.I)
_PROMO_SALE_WORD = re.compile(r"\bsale\b", re.I)


def _is_promo_sentence(s):
    """True when a description fragment is a promo slogan rather than a
    description of what the app does (e.g. "50% OFF!!", "LIMITED TIME!",
    "celebrating the New Universal Build!", an all-caps tagline).
    First-sentence picking skips leading fragments like these so the
    intro is the first functional sentence. Only the wording is
    judged — a normal descriptive sentence is never skipped."""
    t = s.strip()
    if not t:
        return True
    if _PROMO_PCT_OFF.match(t) or _PROMO_FREE_ALONE.match(t):
        return True
    low = t.lower()
    if _PROMO_SALE_WORD.search(low):
        return True
    if any(w in low for w in _PROMO_WORDS):
        return True
    # all-caps short slogan ending with '!' — real descriptions are
    # almost never written entirely in capitals.
    letters = [c for c in t if c.isalpha()]
    if (letters and len(t) <= 60 and t.endswith("!")
            and all(c.isupper() for c in letters)):
        return True
    return False


# Functional verbs: a sentence counts as describing what the app does
# when it contains one of these (whole word for English, substring for
# Chinese), or mentions the app itself. Leading hook / setup fragments
# ("A whole ocean of puzzles.", "Most screen time tools count
# minutes.", "What Matters, at a Glance.") have neither and are passed
# over in favour of the next functional sentence (2026-11-24: Ringo,
# Good Terms, Floaty). Deliberately NOT in the list: generic verbs
# like count / say, which show up in setup sentences.
_FUNCTIONAL_VERBS_EN = (
    "put", "puts", "bring", "brings", "keep", "keeps", "let", "lets",
    "help", "helps", "allow", "allows", "offer", "offers", "track",
    "tracks", "manage", "manages", "create", "creates", "record",
    "records", "remind", "reminds", "import", "imports", "play",
    "plays", "learn", "practise", "practice", "explore", "explores",
    "choose", "chooses", "build", "builds", "plan", "plans",
    "organize", "organizes", "organise", "organises", "save", "saves",
    "share", "shares", "edit", "edits", "change", "changes", "read",
    "reads", "use", "uses", "get", "gets", "make",
    "makes", "take", "takes", "see", "sees", "show", "shows", "give",
    "gives", "provide", "provides", "turn", "turns", "set", "sets",
    "add", "adds", "check", "checks", "ask", "asks", "log", "logs",
    "logged", "sync", "syncs",
)
_FUNCTIONAL_VERBS_ZH = (
    "显示", "帮", "让", "可以", "支持", "提供", "记录", "管理", "自动",
    "查看", "收藏", "提醒", "同步", "导入", "导出", "创建", "编辑",
    "播放", "学习", "练习", "探索", "选择", "制定", "保存", "分享",
    "使用", "找到", "带来", "实现", "抬手", "一键", "完成", "追踪",
    "倒数", "规划", "整理", "连接", "邀请", "放在",
)
_GENERIC_NAME_WORDS = ("app", "apps", "free", "plus", "lite", "pro",
                       "deluxe", "kids", "jr", "ii", "iii", "hd", "4k")


def _app_tokens(app_name):
    """The app's brand word for the functional check: the first word
    of the name with at least 4 chars (e.g. ringo, bolo, floaty).
    Only the brand word — later name words like 'water' in 'Ringo:
    Water Ring Toss' are ordinary nouns and would match hook sentences
    ('A little water toy.')."""
    for t in re.split(r"[^A-Za-z0-9]+", app_name or ""):
        t = t.lower()
        if len(t) >= 4 and t not in _GENERIC_NAME_WORDS:
            return [t]
    return []


def _is_functional_sentence(p, app_tokens):
    """True when a description fragment says what the app does."""
    low = p.lower()
    for t in app_tokens:
        if re.search(r"\b" + re.escape(t) + r"\b", low):
            return True
    for v in _FUNCTIONAL_VERBS_EN:
        if re.search(r"\b" + re.escape(v) + r"\b", low):
            return True
    for v in _FUNCTIONAL_VERBS_ZH:
        if v in p:
            return True
    return False


def _cap_sentence(p, max_len):
    """Cut a sentence to max_len at a clause boundary, no ellipsis.

    The old hard cut + "…" produced dangling "……" in the Chinese
    intro (2026-11-24: Ni Hao Bolo, Dayfetti). Cutting after a comma /
    clause pause keeps a complete clause instead."""
    if len(p) <= max_len:
        return p
    head = p[:max_len]
    for sep in ("，", "、", "；", "：", ",", ";", ":"):
        i = head.rfind(sep)
        if i > 0:
            return head[:i].rstrip()
    i = head.rfind(" ")
    if i > 0:
        return head[:i].rstrip()
    return head.rstrip()


def first_sentence(text, app_name=""):
    """First functional sentence of a description (whole sentence, no
    length cap — callers cap the result where the length matters).

    Splits on Chinese terminators (。！？) and on English sentence ends
    (. ! ? followed by a space), so an English description yields a real
    first sentence instead of an arbitrary 70-char cut. Leading promo
    slogans are skipped (see _is_promo_sentence), and a leading hook /
    setup fragment with no functional verb and no mention of the app is
    passed over in favour of the first functional sentence; if no
    fragment qualifies, the first usable fragment of at least 20 chars
    is kept, then any fragment of at least 8 chars, rather than
    returning nothing.
    """
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"[。！？\n]|(?<=[.!?])\s+", text)
    tokens = _app_tokens(app_name)

    first = ""      # first non-promo functional fragment
    first_long = ""  # first non-promo fragment >= 20 chars
    first_any = ""  # first fragment >= 8 chars, promo or not
    for p in parts:
        p = p.strip()
        if len(p) < 8:
            continue
        if not first_any:
            first_any = p
        if _is_promo_sentence(p):
            continue
        if not first_long and len(p) >= 20:
            first_long = p
        if not first and _is_functional_sentence(p, tokens):
            first = p
            break
    picked = first or first_long or first_any
    if not picked:
        return text[:200]
    return picked


def _polish_intro(s):
    """Normalize a finished Chinese intro: 您 -> 你 (the translator's
    formal 'your' reads stiff in a one-line app blurb — 2026-11-24:
    Petals '您的周期'), and drop any dangling ellipsis left by an
    older truncation."""
    s = (s or "").strip()
    s = s.replace("您", "你")
    # Strip a dangling ellipsis ("…", "……", "...") but keep a single
    # full stop: a normal sentence ends with 。/!/? or one ".".
    s = re.sub(r"(…+|[.]{2,})$", "", s).rstrip()
    return s


def _cap_zh(s, max_len=70):
    """Cap a Chinese intro at max_len chars at a clause boundary."""
    return _cap_sentence(s, max_len)


# Translation chain (tried in order; each level's result must contain
# Chinese and differ from the source, otherwise it counts as failed):
#   1. Google Translate web endpoint (gtx) — backoff retries.
#   2. Google dict-chrome-ex endpoint — 2 retries.
#   3. MyMemory free API — skipped for the rest of the run once its
#      daily quota is exhausted (HTTP 429 or a quota warning in the
#      response).
# Deliberately NOT tried (verified dead 2026-11-24): Lingva (lingva.ml,
# "Translation provider temporarily unavailable"), LibreTranslate.com
# (needs an API key now), translate.terraprint.co / libretranslate.de
# (empty responses), Baidu transapi (empty response). Do not re-add
# them without re-verifying they work.
_TRANSLATE_BACKOFF = (5, 15, 45)   # gtx retries
_DICT_BACKOFF = (2, 5)             # dict-chrome-ex retries
_GOOGLE_DOWN = False    # gtx failed with 429: skip it, rest of the run
_MYMEMORY_DOWN = False  # MyMemory quota exhausted: skip it, rest of run


def _valid_zh(out, src):
    """A usable translation: non-empty, Chinese, different from source."""
    return bool(out) and out != src and any(
        "\u4e00" <= ch <= "\u9fff" for ch in out)


def _translate_attempts(fn, text, waits, label):
    """Call fn(text) with backoff retries. Returns (result, rate_limited):
    rate_limited is True when an attempt got HTTP 429. Sleeps 0.5s
    before every attempt so calls are staggered — on 2026-11-24 all 17
    translation failures landed in the same second, tripping the
    per-minute limit."""
    rate_limited = False
    for attempt, wait in enumerate((0,) + tuple(waits)):
        if attempt:
            print(f"  [translate] {label} retry {attempt} after {wait}s")
            time.sleep(wait)
        time.sleep(0.5)
        try:
            out = fn(text)
        except urllib.error.HTTPError as e:
            print(f"  [translate] {label} failed: {e}")
            if e.code == 429:
                rate_limited = True
            out = ""
        except Exception as e:
            print(f"  [translate] {label} failed: {e}")
            out = ""
        if out:
            return (out, rate_limited)
    return ("", rate_limited)


def _google_translate(text):
    """One attempt against the free Google Translate web endpoint
    (translate.googleapis.com, client=gtx). No API key, stdlib only.
    Returns translated text ('' when the response has none); raises on
    HTTP/network failure so the caller can retry."""
    q = urllib.parse.quote(text)
    url = ("https://translate.googleapis.com/translate_a/single"
           f"?client=gtx&sl=en&tl=zh-CN&dt=t&q={q}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode())
    return "".join(seg[0] for seg in d[0] if seg and seg[0]).strip()


def _dict_chrome_translate(text):
    """One attempt against Google's dict-chrome-ex endpoint
    (clients5.google.com). Response is JSON like ["translated text"] —
    a flat list whose first element is the translation (an older shape
    nests it one level deeper, so both are handled). Returns translated
    text ('' when the response has none); raises on HTTP/network
    failure so the caller can retry."""
    q = urllib.parse.quote(text)
    url = ("https://clients5.google.com/translate_a/t"
           f"?client=dict-chrome-ex&sl=en&tl=zh-CN&q={q}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode())
    if isinstance(d, list) and d:
        first = d[0]
        if isinstance(first, list) and first:
            return (first[0] or "").strip()
        if isinstance(first, str):
            return first.strip()
    return ""


def _mymemory_translate(text):
    """One attempt against the MyMemory free API (no key). Returns
    (translated_text, quota_exhausted). translated_text is '' when the
    response carries no usable translation; quota_exhausted is True
    when the daily anonymous quota is used up (a 429 responseStatus or
    a quota warning inside translatedText — an HTTP 429 is raised as an
    exception instead and handled by the caller)."""
    q = urllib.parse.quote(text)
    url = ("https://api.mymemory.translated.net/get"
           f"?q={q}&langpair=en|zh-CN")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode())
    status = str(d.get("responseStatus"))
    out = (d.get("responseData") or {}).get("translatedText", "") or ""
    out = out.strip()
    if status == "429" or "MYMEMORY WARNING" in out:
        return ("", True)
    if status != "200" or not out or "QUERY LENGTH LIMIT" in out:
        return ("", False)
    return (out, False)


def translate_en_to_zh(text):
    """Translate a short English sentence to Chinese via the three-level
    chain (Google gtx -> dict-chrome-ex -> MyMemory; each level must
    yield Chinese different from the source). Returns (text, provider)
    where provider is "google", "dict-chrome-ex", "mymemory" or ""
    when every level failed — the caller decides the fallback."""
    global _GOOGLE_DOWN, _MYMEMORY_DOWN
    if not text:
        return ("", "")
    if not _GOOGLE_DOWN:
        out, limited = _translate_attempts(
            _google_translate, text, _TRANSLATE_BACKOFF, "google")
        if _valid_zh(out, text):
            return (out, "google")
        if limited:
            _GOOGLE_DOWN = True
    else:
        print("  [translate] google rate-limited earlier, skipping gtx")
    out, _ = _translate_attempts(
        _dict_chrome_translate, text, _DICT_BACKOFF, "dict-chrome-ex")
    if _valid_zh(out, text):
        return (out, "dict-chrome-ex")
    if not _MYMEMORY_DOWN:
        time.sleep(0.5)
        try:
            out, quota = _mymemory_translate(text)
        except urllib.error.HTTPError as e:
            quota = (e.code == 429)
            if not quota:
                print(f"  [translate] fallback failed: {e}")
            out = ""
        except Exception as e:
            print(f"  [translate] fallback failed: {e}")
            out, quota = "", False
        if quota:
            _MYMEMORY_DOWN = True
            print("  [translate] MyMemory quota exhausted; "
                  "skipping MyMemory for the rest of this run")
        elif _valid_zh(out, text):
            return (out, "mymemory")
    else:
        print("  [translate] MyMemory quota exhausted earlier, skipping")
    return ("", "")


def chinese_intro(app_id, us_record):
    """One-line Chinese intro.

    1. China App Store description, first sentence (when it is Chinese).
    2. Otherwise machine-translate the US description's first sentence
       (three-level chain: Google gtx -> dict-chrome-ex -> MyMemory).
    3. If translation is unavailable, keep the English first sentence so
       the post still says what the app does (logged as a warning).
    4. No description at all: a generic Chinese line from name + genre.
    The raw iTunes record is never modified.
    """
    name = us_record.get("trackName", "")
    cn = lookup(app_id, country="CN")
    if cn and cn.get("description"):
        s = first_sentence(cn["description"], app_name=name)
        if s and any("\u4e00" <= ch <= "\u9fff" for ch in s):
            print(f"  [intro] {app_id}: via cn-official")
            return _polish_intro(_cap_zh(s))
    if us_record.get("description"):
        # No length cap on the English sentence: a long English
        # sentence usually translates short, and capping it first is
        # what left dangling "……" in the intro. Cap the Chinese.
        s = first_sentence(us_record["description"], app_name=name)
        if s:
            zh, provider = translate_en_to_zh(s)
            if zh and any("\u4e00" <= ch <= "\u9fff" for ch in zh):
                print(f"  [intro] {app_id}: via {provider}")
                return _polish_intro(_cap_zh(zh))
            print(f"  [intro] {app_id}: translation unavailable, "
                  f"keeping English intro")
            return _polish_intro(_cap_sentence(s, 70))
    genre = (us_record.get("primaryGenreName") or "应用")
    return f"{us_record.get('trackName', '')}是一款{genre}应用。"


def download_image(url, path):
    """Download an image, normalize to JPEG via PIL, save to path."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except Exception as e:
        print(f"  [img] download failed {url}: {e}")
        return False
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(data)).convert("RGB")
        im.save(path, "JPEG", quality=88)
        return True
    except Exception as e:
        print(f"  [img] PIL convert failed {url}: {e}")
        return False


# ---------------- cover ----------------

# CJK fonts for the cover. DejaVu has no CJK glyphs, so Chinese rendered
# with it comes out as boxes. Preferred order: Noto Sans CJK SC .otf
# (GitHub runner — the workflow installs fonts-noto-cjk), then the
# NotoSansCJK .ttc collections (index 0 renders CJK), then DejaVu
# (Latin only, last resort — Chinese will show as boxes).
CJK_FONT_BOLD = [
    "/usr/share/fonts/truetype/noto/NotoSansCJKsc-Bold.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
]
CJK_FONT_REGULAR = [
    "/usr/share/fonts/truetype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


def _load_cover_font(candidates, size):
    """First usable font from candidates; .ttc needs index=0."""
    from PIL import ImageFont
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            if path.endswith(".ttc"):
                f = ImageFont.truetype(path, size, index=0)
            else:
                f = ImageFont.truetype(path, size)
            print(f"  [cover] font: {path}")
            return f
        except Exception:
            continue
    return None


def make_cover(icon_paths, out_path, date_str, n_apps, n_iaps=0):
    """1200x630 dark cover: featured icons + title text.

    The title and date lines are Chinese, so they must be drawn with a
    CJK font (Noto Sans CJK SC). DejaVu has no CJK glyphs and renders
    them as boxes — the 2026-11-23 cover was all boxes for this reason.

    Icons come from pick_cover_icons: the featured apps when there
    are any, else the day's Chinese apps (at most 4). When no icon
    loads at all, the lower 70% of the canvas must not be left blank —
    in Telegram dark mode blank dark space reads as a broken image
    (2026-11-24: 0 featured, the blank cover looked broken). Instead
    a large translucent gold "免" watermark is drawn in the icon band
    with a stats line at the bottom.
    """
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), (18, 18, 24))
    d = ImageDraw.Draw(img)
    # subtle gold accent bar
    d.rectangle([0, 0, W, 10], fill=(212, 175, 55))
    font_big = _load_cover_font(CJK_FONT_BOLD, 64)
    if font_big is None:
        print("  [cover] WARNING: no CJK font found, Chinese will render "
              "as boxes (DejaVu fallback)")
        try:
            font_big = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
        except Exception:
            font_big = ImageFont.load_default()
    font_small = _load_cover_font(CJK_FONT_REGULAR, 36)
    if font_small is None:
        print("  [cover] WARNING: no CJK font found, Chinese will render "
              "as boxes (DejaVu fallback)")
        try:
            font_small = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        except Exception:
            font_small = ImageFont.load_default()
    d.text((60, 60), "今日限免", font=font_big, fill=(245, 245, 245))
    # Subtitle counts both kinds: a 0-paid day must not read as an
    # empty day ("0 款完全免费", 2026-11-24 round 3).
    if n_apps:
        sub = f"{date_str} · {n_apps} 款完全免费"
        if n_iaps:
            sub += f" · {n_iaps} 个内购"
    else:
        sub = f"{date_str} · {n_iaps} 个内购 0 元兑"
    d.text((60, 150), sub, font=font_small, fill=(200, 200, 210))
    # Featured icons, centered: up to 4 icons. 1-3 icons stay 240px
    # (the verified layout: 3 x 240 + 2 x 40 gaps = 800px wide,
    # starting at x=200, so the right side is no longer empty black).
    # 4 icons shrink to 220px: 4 x 220 + 3 x 40 gaps = 1000px wide,
    # still centered on the 1200px canvas.
    icon_size = 220 if len(icon_paths) >= 4 else 240
    loaded = []
    for p in icon_paths[:4]:
        try:
            loaded.append(Image.open(p).convert("RGB").resize((icon_size, icon_size)))
        except Exception:
            continue
    if loaded:
        total_w = len(loaded) * icon_size + (len(loaded) - 1) * 40
        x = (W - total_w) // 2
        # Icons are square JPEGs; round the corners to the iOS icon
        # proportion (~22.5% of the side) so the cover reads like real
        # App Store artwork instead of raw squares (2026-11-24).
        mask = Image.new("L", (icon_size, icon_size), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, icon_size, icon_size],
            radius=int(icon_size * 0.225), fill=255)
        for icon in loaded:
            img.paste(icon, (x, 300), mask)
            x += icon_size + 40
    else:
        # Decorative fallback (no icons at all): a large translucent
        # gold "免" watermark centred in the icon band, plus a stats
        # line at the bottom. The cover must never be 70% empty dark
        # space (2026-11-24: 0 featured, the blank cover looked broken
        # in the channel's dark theme).
        wm_font = _load_cover_font(CJK_FONT_BOLD, 260)
        if wm_font is not None:
            overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            od = ImageDraw.Draw(overlay)
            bbox = od.textbbox((0, 0), "免", font=wm_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            od.text(((W - tw) // 2 - bbox[0], 400 - th // 2 - bbox[1]),
                    "免", font=wm_font, fill=(212, 175, 55, 64))
            img = Image.alpha_composite(img.convert("RGBA"),
                                        overlay).convert("RGB")
            d = ImageDraw.Draw(img)
        stats = f"今日 {n_apps} 款免费 · {n_iaps} 个内购"
        sb = d.textbbox((0, 0), stats, font=font_small)
        d.text(((W - (sb[2] - sb[0])) // 2 - sb[0], 570),
               stats, font=font_small, fill=(200, 200, 210))
    img.save(out_path, "JPEG", quality=88)
    print(f"  cover -> {out_path}")


# ---------------- blog post ----------------

def esc(s):
    return s.replace("|", "｜")


def _post_paid_app_lines(a, i, asset_dir, ymd, level, languages=None):
    """Markdown lines for one paid app in the blog post.

    level 3 = flat list (### N. Name), level 4 = inside a category group
    (#### N. Name). The header image is the same wide banner as the
    channel post; fall back to the icon when it could not be built.

    Canonical field order (2026-11-24 audit item 7, shared with the
    WeChat article): 原价 / 评分 / 设备 / 大小 / 语言 / 简介 / 领取.
    Rating is '★4.3（13）' (item 8) and the line is omitted when the
    app has no rating."""
    header = (f"banner-{a['id']}.jpg"
              if os.path.isfile(os.path.join(
                  asset_dir, f"banner-{a['id']}.jpg"))
              else f"{a['id']}.jpg")
    h = "#" * level
    lines = [
        f"{h} {i}. {a['name']}",
        "",
        f"![{a['name']}](../assets/free-apps-{ymd}/{header})",
        "",
        f"- **原价**：${a['price_usd']:.2f}，现在免费" if a["price_usd"]
        else "- **原价**：付费应用，现在免费",
    ]
    if a.get("rating"):
        lines.append(
            f"- **评分**：★{a['rating']:.1f}（{a['rating_count']:,}）")
    lines += [
        f"- **设备**：{a['devices']}",
        f"- **最低系统**：iOS {a['min_os']}",
    ]
    size = format_size(a.get("size_bytes"))
    if size:
        lines.append(f"- **大小**：{size}")
    lang_txt = format_langs((languages or {}).get(str(a["id"]), []))
    if lang_txt:
        lines.append(f"- **语言**：{lang_txt}")
    lines += [
        f"- **简介**：{a['intro']}",
        f"- **领取**：[在 App Store 打开](https://apps.apple.com/us/app/id{a['id']})",
        "",
        "!carousel",
        f"![{a['name']} 预览 1](../assets/free-apps-{ymd}/shots/{a['id']}-1.jpg)",
        f"![{a['name']} 预览 2](../assets/free-apps-{ymd}/shots/{a['id']}-2.jpg)",
        "",
    ]
    return lines


def _post_iap_app_lines(a, i, asset_dir, ymd, level, languages=None):
    """Markdown lines for one IAP promo in the blog post (level 3 flat,
    level 4 inside a category group).

    Canonical field order (item 7): 内购 / 原价 / 评分 / 设备 / 大小 /
    语言 / 简介 / 兑换链接 / App 链接. No rating -> the line is omitted
    (was '暂无评分', item 8)."""
    header = (f"banner-{a['id']}.jpg"
              if os.path.isfile(os.path.join(
                  asset_dir, f"banner-{a['id']}.jpg"))
              else f"iap/{a['id']}.jpg")
    h = "#" * level
    section_lines = [
        f"{h} {i}. {a['name']}",
        "",
        f"![{a['name']}](../assets/free-apps-{ymd}/{header})",
        "",
        f"- **内购**：{a['iap_name']}",
        f"- **原价**：${a['iap_price']:.2f}，兑换码 0 元领" if a.get("iap_price")
        else "- **原价**：兑换码 0 元领",
    ]
    if a.get("rating"):
        section_lines.append(
            f"- **评分**：★{a['rating']:.1f}（{a['rating_count']:,}）")
    section_lines += [
        f"- **设备**：{a['devices']}",
        f"- **最低系统**：iOS {a['min_os']}",
    ]
    size = format_size(a.get("size_bytes"))
    if size:
        section_lines.append(f"- **大小**：{size}")
    lang_txt = format_langs((languages or {}).get(str(a["id"]), []))
    if lang_txt:
        section_lines.append(f"- **语言**：{lang_txt}")
    section_lines.append(f"- **简介**：{a['intro']}")
    if a.get("redeem_url"):
        section_lines.append(
            f"- **兑换链接**：[点这里兑换]({a['redeem_url']})")
    section_lines += [
        f"- **App 链接**：[在 App Store 打开](https://apps.apple.com/us/app/id{a['id']})",
        "!carousel",
        f"![预览 1](../assets/free-apps-{ymd}/iap-shots/{a['id']}-1.jpg)",
        f"![预览 2](../assets/free-apps-{ymd}/iap-shots/{a['id']}-2.jpg)",
        "",
    ]
    return section_lines


def _known_total(amounts):
    """Sum of known $ prices, or None when every price is unknown.

    A price of None means the original price was never captured; it
    must not count as $0 — "原价加起来约 0 美元" on a day that does
    have paid apps (2026-11-24: Mix and Match Two) is wrong."""
    known = [a for a in amounts if a is not None]
    return sum(known) if known else None


def _title_suffix(paid, iaps):
    """'N 款付费应用免费领＋M 个终身内购 0 元兑', empty parts dropped."""
    parts = []
    if paid:
        parts.append(f"{len(paid)} 款付费应用免费领")
    if iaps:
        parts.append(f"{len(iaps)} 个终身内购 0 元兑")
    return "＋".join(parts)


def _lead_sentences(paid, iaps, total_paid, total_iap):
    """The day's lead: paid clause, IAP clause, or both.

    A 0-paid day says so plainly and leads with the IAPs instead of
    claiming '0 款……免费领' (2026-11-24 round 3). A total is only
    mentioned when at least one price is known."""
    sents = []
    if paid:
        s = f"今天 {len(paid)} 款付费 App 限时免费"
        if total_paid is not None:
            s += f"，原价加起来约 {total_paid:.0f} 美元"
        sents.append(s)
    if iaps:
        s = (f"另有 {len(iaps)} 个终身内购可用兑换码 0 元领"
             if paid else
             f"今天没有付费应用限免，另有 {len(iaps)} 个终身内购可用兑换码 0 元领")
        if total_iap is not None:
            s += f"，原价加起来约 {total_iap:.0f} 美元"
        sents.append(s)
    return "；".join(sents) + "。"


def _claim_tail(paid):
    """How to claim, for the excerpt / lead tail (item 11: the old
    text only described the paid-app '获取' flow)."""
    if paid:
        return "点链接进 App Store 点“获取”就行，限免随时结束，看到就领。"
    return "点帖子里的兑换链接进 App Store 兑，限免随时结束，看到就领。"


def write_post(date, paid, iaps, featured, asset_dir, languages=None):
    """Write posts/<date>-free-apps.md in the 2026-11-23 format."""
    ymd = date.replace("-", "")
    slug = f"free-apps-{ymd}"
    total_paid = _known_total([a.get("price_usd") for a in paid])
    total_iap = _known_total([a.get("iap_price") for a in iaps])
    title = f"今日限免 App（{date}）：{_title_suffix(paid, iaps)}"
    lead = _lead_sentences(paid, iaps, total_paid, total_iap)
    excerpt = lead + _claim_tail(paid)
    lines = [
        "---",
        f"title: {title}",
        f"date: {date}",
        "tag: 应用限免",
        "tagkey: free-apps",
        f"slug: {slug}",
        f"cover: free-apps-{ymd}/cover.jpg",
        f"excerpt: {excerpt}",
        "---",
        "",
        (lead + "都是今天刚确认的，限免随时可能结束，看到喜欢的就"
         + ("领。" if paid else "兑。")),
        "",
    ]
    # Empty featured (no Chinese app that day): omit the whole
    # recommendation section, no bare heading left behind.
    if featured:
        lines += ["## 今日极力推荐", ""]
        for i, a in enumerate(featured, 1):
            # price_usd can be None (AppRaven-sourced apps carry no price);
            # the per-app section already falls back to '付费应用', do the
            # same here instead of formatting None (TypeError).
            fprice = (f"${a['price_usd']:.2f}" if a["price_usd"]
                      else "付费应用")
            lines.append(
                f"{i}. **{a['name']}** — 评分 {a['rating']:.1f}，原价 "
                f"{fprice}，{a['intro']}")
        lines += ["", ""]
    # Empty paid day: omit the whole paid section, no bare heading
    # left behind (same rule as the empty featured section above).
    if paid:
        lines += [f"## 付费应用限时免费（{len(paid)} 款）", "",
                  "点链接进 App Store 点“获取”就行。领的时候只点“获取”，不要买任何内购。",
                  ""]
        # Category groups (### <category> + #### apps) when 2+ categories are
        # present; a lone category stays a flat list (### apps, as before).
        paid_groups = group_by_category(paid)
        grouped_paid = len(paid_groups) >= 2
        if grouped_paid:
            for cat, apps in paid_groups:
                lines += [f"### {cat}（{len(apps)} 款）", ""]
                for i, a in enumerate(apps, 1):
                    lines += _post_paid_app_lines(a, i, asset_dir, ymd, 4,
                                                  languages)
        else:
            for i, a in enumerate(paid, 1):
                lines += _post_paid_app_lines(a, i, asset_dir, ymd, 3,
                                              languages)
    if iaps:
        lines += [
            f"## 终身内购 0 元兑换（{len(iaps)} 个）",
            "",
            "这几个不是商店里直接降价到 0 元，而是开发者发的公开兑换码："
            "点帖子里的兑换链接直接进 App Store 兑。每个兑换码一个 Apple "
            "账号只能用一次，都是终身解锁、不是订阅，不会续费。",
            "",
            "**怎么领**：先装上对应的免费 App → 点该款下面的兑换链接 → "
            "自动跳到 App Store 兑换页，确认就行。不用绑卡，没有试用期。"
            "没有兑换链接的款，暂时只能先装 App，等开发者放出公开码。",
            "",
        ]
        iap_groups = group_by_category(iaps)
        grouped_iap = len(iap_groups) >= 2
        if grouped_iap:
            for cat, apps in iap_groups:
                lines += [f"### {cat}（{len(apps)} 个）", ""]
                for i, a in enumerate(apps, 1):
                    lines += _post_iap_app_lines(a, i, asset_dir, ymd, 4,
                                                 languages)
        else:
            for i, a in enumerate(iaps, 1):
                lines += _post_iap_app_lines(a, i, asset_dir, ymd, 3,
                                             languages)
    lines += ["---", "", "限免结束时间苹果不公布，一般 1–3 天，尽快领。", ""]
    path = os.path.join(POSTS_DIR, f"{date}-free-apps.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  post -> {path}")
    return path


# ---------------- wechat / xiaohongshu ----------------

def _banner_image(a, asset_dir, iap=False):
    """Image file to use for an app: banner-<id>.jpg when built, else the
    app icon. Returns the path relative to assets/ (for display)."""
    if os.path.isfile(os.path.join(asset_dir, f"banner-{a['id']}.jpg")):
        return f"banner-{a['id']}.jpg"
    if iap:
        return f"iap/{a['id']}.jpg"
    return f"{a['id']}.jpg"


def _wechat_paid_app_lines(a, i, languages, level):
    """Markdown lines for one paid app in wechat.md (level 3 flat,
    level 4 inside a category group)."""
    lang_txt = format_langs(languages.get(str(a["id"]), []))
    h = "#" * level
    lines = [
        f"{h} {i}. {a['name']}",
        "",
        f"**原价**：${a['price_usd']:.2f}，现在免费" if a["price_usd"]
        else "**原价**：付费应用，现在免费",
    ]
    if a.get("rating"):
        lines.append(
            f"**评分**：★{a['rating']:.1f}（{a['rating_count']:,}）")
    lines.append(f"**设备**：{a['devices']}，最低 iOS {a['min_os']}")
    size = format_size(a.get("size_bytes"))
    if size:
        lines.append(f"**大小**：{size}")
    if lang_txt:
        lines.append(f"**语言**：{lang_txt}")
    lines += [
        f"**简介**：{a['intro']}",
        f"**领取**：[在 App Store 打开](https://apps.apple.com/us/app/id{a['id']})",
        "",
    ]
    return lines


def _wechat_iap_app_lines(a, i, languages, level):
    """Markdown lines for one IAP promo in wechat.md (level 3 flat,
    level 4 inside a category group)."""
    lang_txt = format_langs(languages.get(str(a["id"]), []))
    h = "#" * level
    lines = [
        f"{h} {i}. {a['name']}",
        "",
        f"**内购**：{a['iap_name']}",
        f"**原价**：${a['iap_price']:.2f}，兑换码 0 元领" if a.get("iap_price")
        else "**原价**：兑换码 0 元领",
    ]
    if a.get("rating"):
        lines.append(
            f"**评分**：★{a['rating']:.1f}（{a['rating_count']:,}）")
    lines.append(
        f"**设备**：{a['devices']}，最低 iOS {a['min_os']}")
    size = format_size(a.get("size_bytes"))
    if size:
        lines.append(f"**大小**：{size}")
    if lang_txt:
        lines.append(f"**语言**：{lang_txt}")
    lines += [
        f"**简介**：{a['intro']}",
    ]
    if a.get("redeem_url"):
        lines.append(f"**兑换链接**：[点这里兑换]({a['redeem_url']})")
    lines += [
        f"**App 链接**：[在 App Store 打开](https://apps.apple.com/us/app/id{a['id']})",
        "",
    ]
    return lines


def write_wechat(date, paid, iaps, featured, languages, asset_dir):
    """Write automation/data/<date>/wechat.md — a copy-paste-ready WeChat
    Official Account article (Markdown). Cover image: upload
    assets/free-apps-<ymd>/cover.jpg as the cover in the WeChat editor.
    No Telegram emoji pile-up; plain sections, App Store links kept
    (WeChat articles can carry them)."""
    ymd = date.replace("-", "")
    total_paid = _known_total([a.get("price_usd") for a in paid])
    total_iap = _known_total([a.get("iap_price") for a in iaps])
    if paid:
        wc_title = f"{len(paid)} 款付费 App 限时免费"
    else:
        wc_title = f"{len(iaps)} 个终身内购 0 元兑"
    lead = _lead_sentences(paid, iaps, total_paid, total_iap)
    lines = [
        f"# 今日限免｜{wc_title}",
        "",
        f"封面图：assets/free-apps-{ymd}/cover.jpg（在公众号编辑器里把这张图设为封面）",
        "",
        lead + "限免随时可能结束，看到喜欢的就"
        + ("领。" if paid else "兑。"),
        "",
    ]
    if featured:
        lines += ["## 今日极力推荐", ""]
        for i, a in enumerate(featured, 1):
            price = f"${a['price_usd']:.2f}" if a["price_usd"] else "付费"
            lines.append(
                f"{i}. **{a['name']}**——{a['intro']}（原价 {price}，"
                f"评分 {a['rating']:.1f}）")
        lines += ["", ""]
    if paid:
        lines += [f"## 付费应用限时免费（{len(paid)} 款）", "",
                  "点链接进 App Store 点“获取”就行。领的时候只点“获取”，不要买任何内购。",
                  ""]
        wechat_paid_groups = group_by_category(paid)
        grouped = len(wechat_paid_groups) >= 2
        if grouped:
            for cat, apps in wechat_paid_groups:
                lines += [f"### {cat}（{len(apps)} 款）", ""]
                for i, a in enumerate(apps, 1):
                    lines += _wechat_paid_app_lines(a, i, languages, 4)
        else:
            for i, a in enumerate(paid, 1):
                lines += _wechat_paid_app_lines(a, i, languages, 3)
    if iaps:
        lines += [
            f"## 终身内购 0 元兑换（{len(iaps)} 个）",
            "",
            "这几个不是商店里直接降价到 0 元，而是开发者发的公开兑换码："
            "点下面的兑换链接直接进 App Store 兑。每个兑换码一个 Apple "
            "账号只能用一次，都是终身解锁、不是订阅，不会续费。",
            "",
            "**怎么领**：先装上对应的免费 App，再点该款下面的兑换链接，"
            "自动跳到 App Store 兑换页确认就行。不用绑卡，没有试用期。"
            "没有兑换链接的款，暂时只能先装 App，等开发者放出公开码。",
            "",
        ]
        wechat_iap_groups = group_by_category(iaps)
        grouped_iap = len(wechat_iap_groups) >= 2
        if grouped_iap:
            for cat, apps in wechat_iap_groups:
                lines += [f"### {cat}（{len(apps)} 个）", ""]
                for i, a in enumerate(apps, 1):
                    lines += _wechat_iap_app_lines(a, i, languages, 4)
        else:
            for i, a in enumerate(iaps, 1):
                lines += _wechat_iap_app_lines(a, i, languages, 3)
    lines += ["---", "", "限免结束时间苹果不公布，一般 1–3 天，尽快领。", ""]
    path = os.path.join(DATA_DIR, date, "wechat.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  wechat -> {path}")
    return path


def write_xiaohongshu(date, paid, iaps, asset_dir):
    """Write automation/data/<date>/xiaohongshu.txt — a copy-paste-ready
    Xiaohongshu note. No external links anywhere (Xiaohongshu blocks
    them): readers are told to search the app name in the App Store.
    Images to post are listed at the end (banner-<id>.jpg), in the
    same grouped order as the body text (item 2: the old paid+iaps
    raw order mismatched the grouped body and mispaired images).
    IAP entries print the public redeem code itself (item 3): without
    a code the note is unusable, since no link can be tapped."""
    ymd = date.replace("-", "")
    total_paid = _known_total([a.get("price_usd") for a in paid])
    total_iap = _known_total([a.get("iap_price") for a in iaps])
    if paid:
        xhs_title = f"今日限免｜这 {len(paid)} 款付费 App 白嫖，手慢无"
        xhs_lead = f"今天 {len(paid)} 款付费 App 限时免费"
        if total_paid is not None:
            xhs_lead += f"，原价加起来约 {total_paid:.0f} 美元"
        xhs_lead += "，全部 0 元领，限免随时结束，看到就冲！"
        search_line = ("在 App Store 搜下面每个应用的名字，点“获取”就行，"
                       "只点获取，别买内购。")
    else:
        xhs_title = f"今日限免｜{len(iaps)} 个终身内购 0 元兑，手慢无"
        xhs_lead = "今天没有付费应用限免，"
        xhs_lead += f"另有 {len(iaps)} 个终身内购 0 元兑"
        if total_iap is not None:
            xhs_lead += f"，原价加起来约 {total_iap:.0f} 美元"
        xhs_lead += "，限免随时结束，看到就冲！"
        search_line = ("在 App Store 搜下面每个应用的名字，先装上 App，"
                       "再用每款下面的兑换码兑换。")
    lines = [
        xhs_title,
        "",
        xhs_lead,
        "",
        search_line,
        "",
    ]
    ordered = []  # (app, is_iap) in body order, for the image list
    xhs_paid_groups = group_by_category(paid)
    if len(xhs_paid_groups) >= 2:
        for cat, apps in xhs_paid_groups:
            lines += [f"【{cat}】", ""]
            for i, a in enumerate(apps, 1):
                ordered.append((a, False))
                price = (f"原价 ${a['price_usd']:.2f} → 免费" if a["price_usd"]
                         else "付费应用 → 免费")
                lines.append(
                    f"{i}. {a['name']}：{a['intro']}（{price}，评分 {a['rating']:.1f}）")
            lines.append("")
    else:
        for i, a in enumerate(paid, 1):
            ordered.append((a, False))
            price = (f"原价 ${a['price_usd']:.2f} → 免费" if a["price_usd"]
                     else "付费应用 → 免费")
            lines.append(
                f"{i}. {a['name']}：{a['intro']}（{price}，评分 {a['rating']:.1f}）")
    if iaps:
        lines += ["", "终身内购 0 元兑：", ""]
        xhs_iap_groups = group_by_category(iaps)
        if len(xhs_iap_groups) >= 2:
            for cat, apps in xhs_iap_groups:
                lines += [f"【{cat}】", ""]
                for i, a in enumerate(apps, 1):
                    ordered.append((a, True))
                    price = (f"原价 ${a['iap_price']:.2f}" if a.get("iap_price")
                             else "原价不详")
                    code_txt = (f"兑换码：{a['redeem_code']}"
                                if a.get("redeem_code") else "兑换码待公布")
                    lines.append(
                        f"{i}. {a['name']}（{a['iap_name']}，{price}，{code_txt}）："
                        f"{a['intro']}")
                lines.append("")
        else:
            for i, a in enumerate(iaps, 1):
                ordered.append((a, True))
                price = (f"原价 ${a['iap_price']:.2f}" if a.get("iap_price")
                         else "原价不详")
                code_txt = (f"兑换码：{a['redeem_code']}"
                            if a.get("redeem_code") else "兑换码待公布")
                lines.append(
                    f"{i}. {a['name']}（{a['iap_name']}，{price}，{code_txt}）："
                    f"{a['intro']}")
        lines += [
            "",
            "内购兑换方式：先装上 App，再进 App Store 兑换页输入上面每款对应的兑换码；"
            "没有兑换码的款，暂时只能先装 App，等开发者放出公开码。",
        ]
    lines += [
        "",
        "#应用限免 #限时免费 #iPhone必备 #免费App #薅羊毛 #苹果应用 #今日限免",
        "",
        "配图（按顺序发，每款一张）：",
    ]
    for a, is_iap in ordered:
        lines.append(
            f"- {_banner_image(a, asset_dir, iap=is_iap)}（{a['name']}"
            f"{'·内购' if is_iap else ''}）")
    lines.append(f"封面可用：assets/free-apps-{ymd}/cover.jpg")
    path = os.path.join(DATA_DIR, date, "xiaohongshu.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  xiaohongshu -> {path}")
    return path


# Images for the WeChat HTML version. The blog itself is login-gated, so
# its pages.dev asset URLs 302 to /login and the WeChat editor cannot
# fetch them; the repo is public, so the same image files are served
# directly from raw.githubusercontent.com.
RAW_GITHUB_BASE = "https://raw.githubusercontent.com/aliporcins/devlog/main"


def _raw_img_url(asset_rel):
    """Absolute raw-GitHub URL for an asset/ path (WeChat-fetchable)."""
    return f"{RAW_GITHUB_BASE}/assets/{asset_rel}"


def _wechat_html_paid_card(a, i, languages, asset_dir, ymd):
    """One paid app's card <div> for wechat.html."""
    esc = html.escape
    lang_txt = format_langs(languages.get(str(a["id"]), []))
    img_file = _banner_image(a, asset_dir)
    img_url = _raw_img_url(f"free-apps-{ymd}/{img_file}")
    h = []
    h.append('<div style="background:#fafafa;border:1px solid #eeeeee;'
             'border-radius:8px;padding:16px;margin:0 0 16px;">')
    h.append(f'<p style="margin:0 0 12px;"><img src="{img_url}" '
             f'alt="{esc(a["name"])}" style="width:100%;display:block;border-radius:6px;"></p>')
    h.append(f'<h3 style="font-size:17px;margin:0 0 8px;color:#222222;">{i}. {esc(a["name"])}</h3>')
    price = (f"${a['price_usd']:.2f}，现在免费" if a["price_usd"]
             else "付费应用，现在免费")
    h.append(f'<p style="margin:6px 0;font-size:15px;color:#444444;"><strong style="color:#222222;">原价：</strong>{price}</p>')
    if a.get("rating"):
        h.append(f'<p style="margin:6px 0;font-size:15px;color:#444444;"><strong style="color:#222222;">评分：</strong>★{a["rating"]:.1f}（{a["rating_count"]:,}）</p>')
    h.append(f'<p style="margin:6px 0;font-size:15px;color:#444444;"><strong style="color:#222222;">设备：</strong>{esc(a["devices"])}，最低 iOS {esc(a["min_os"])}</p>')
    _sz = format_size(a.get("size_bytes"))
    if _sz:
        h.append(f'<p style="margin:6px 0;font-size:15px;color:#444444;"><strong style="color:#222222;">大小：</strong>{_sz}</p>')
    if lang_txt:
        h.append(f'<p style="margin:6px 0;font-size:15px;color:#444444;"><strong style="color:#222222;">语言：</strong>{esc(lang_txt)}</p>')
    h.append(f'<p style="margin:6px 0;font-size:15px;color:#444444;"><strong style="color:#222222;">简介：</strong>{esc(a["intro"])}</p>')
    h.append(f'<p style="margin:6px 0;font-size:15px;"><a href="https://apps.apple.com/us/app/id{a["id"]}" '
             'style="color:#576b95;text-decoration:none;">在 App Store 打开</a></p>')
    h.append("</div>")
    return h


def _wechat_html_iap_card(a, i, languages, asset_dir, ymd):
    """One IAP promo's card <div> for wechat.html."""
    esc = html.escape
    lang_txt = format_langs(languages.get(str(a["id"]), []))
    img_file = _banner_image(a, asset_dir, iap=True)
    img_url = _raw_img_url(f"free-apps-{ymd}/{img_file}")
    h = []
    h.append('<div style="background:#fafafa;border:1px solid #eeeeee;'
             'border-radius:8px;padding:16px;margin:0 0 16px;">')
    h.append(f'<p style="margin:0 0 12px;"><img src="{img_url}" '
             f'alt="{esc(a["name"])}" style="width:100%;display:block;border-radius:6px;"></p>')
    h.append(f'<h3 style="font-size:17px;margin:0 0 8px;color:#222222;">{i}. {esc(a["name"])}</h3>')
    h.append(f'<p style="margin:6px 0;font-size:15px;color:#444444;"><strong style="color:#222222;">内购：</strong>{esc(a["iap_name"])}</p>')
    price = (f"${a['iap_price']:.2f}，兑换码 0 元领" if a.get("iap_price")
             else "兑换码 0 元领")
    h.append(f'<p style="margin:6px 0;font-size:15px;color:#444444;"><strong style="color:#222222;">原价：</strong>{price}</p>')
    if a.get("rating"):
        h.append(f'<p style="margin:6px 0;font-size:15px;color:#444444;"><strong style="color:#222222;">评分：</strong>★{a["rating"]:.1f}（{a["rating_count"]:,}）</p>')
    h.append(f'<p style="margin:6px 0;font-size:15px;color:#444444;"><strong style="color:#222222;">设备：</strong>{esc(a["devices"])}，最低 iOS {esc(a["min_os"])}</p>')
    _sz = format_size(a.get("size_bytes"))
    if _sz:
        h.append(f'<p style="margin:6px 0;font-size:15px;color:#444444;"><strong style="color:#222222;">大小：</strong>{_sz}</p>')
    if lang_txt:
        h.append(f'<p style="margin:6px 0;font-size:15px;color:#444444;"><strong style="color:#222222;">语言：</strong>{esc(lang_txt)}</p>')
    h.append(f'<p style="margin:6px 0;font-size:15px;color:#444444;"><strong style="color:#222222;">简介：</strong>{esc(a["intro"])}</p>')
    if a.get("redeem_url"):
        h.append(f'<p style="margin:6px 0;font-size:15px;"><a href="{esc(a["redeem_url"])}" '
                 'style="color:#576b95;text-decoration:none;">点这里兑换</a></p>')
    h.append(f'<p style="margin:6px 0;font-size:15px;"><a href="https://apps.apple.com/us/app/id{a["id"]}" '
             'style="color:#576b95;text-decoration:none;">在 App Store 打开</a></p>')
    h.append("</div>")
    return h


def write_wechat_html(date, paid, iaps, featured, languages, asset_dir):
    """Write automation/data/<date>/wechat.html — a standalone HTML file
    the user opens in a browser, selects all, copies, and pastes into the
    WeChat Official Account editor. Inline styles only (no external CSS,
    no JS; only tags/styles the WeChat editor keeps). Images are absolute
    raw-GitHub URLs so the editor can fetch and re-upload them."""
    ymd = date.replace("-", "")
    total_paid = _known_total([a.get("price_usd") for a in paid])
    total_iap = _known_total([a.get("iap_price") for a in iaps])
    esc = html.escape
    cover_url = _raw_img_url(f"free-apps-{ymd}/cover.jpg")
    if paid:
        wc_title = f"{len(paid)} 款付费 App 限时免费"
    else:
        wc_title = f"{len(iaps)} 个终身内购 0 元兑"
    lead = _lead_sentences(paid, iaps, total_paid, total_iap)
    h = []
    h.append("<!DOCTYPE html>")
    h.append('<html lang="zh-CN"><head><meta charset="utf-8">')
    h.append(f"<title>今日限免｜{wc_title}</title></head>")
    h.append('<body style="margin:0;padding:0;background:#ffffff;">')
    h.append('<div style="max-width:677px;margin:0 auto;padding:8px 16px 32px;'
             "font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue',"
             "'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;"
             'color:#333333;line-height:1.75;font-size:16px;">')
    h.append('<h1 style="font-size:22px;line-height:1.4;color:#222222;'
             'text-align:center;margin:24px 0 8px;">'
             f"今日限免｜{wc_title}</h1>")
    h.append('<p style="text-align:center;color:#888888;font-size:14px;'
             f'margin:0 0 20px;">{date} · {_title_suffix(paid, iaps)}</p>')
    h.append(f'<p style="text-align:center;margin:0 0 8px;"><img src="{cover_url}" '
             'alt="今日限免封面" style="width:100%;display:block;border-radius:8px;"></p>')
    h.append('<p style="color:#444444;font-size:15px;">'
             f"{lead}限免随时可能结束，看到喜欢的就"
             + ("领。" if paid else "兑。") + "</p>")
    if featured:
        h.append('<h2 style="font-size:18px;color:#222222;border-left:4px solid '
                 '#d4af37;padding-left:10px;margin:28px 0 12px;">今日极力推荐</h2>')
        for i, a in enumerate(featured, 1):
            price = f"${a['price_usd']:.2f}" if a["price_usd"] else "付费"
            h.append('<p style="margin:8px 0;font-size:15px;color:#444444;">'
                     f"<strong style=\"color:#222222;\">{i}. {esc(a['name'])}</strong>"
                     f"——{esc(a['intro'])}（原价 {price}，评分 {a['rating']:.1f}）</p>")
    if paid:
        h.append('<h2 style="font-size:18px;color:#222222;border-left:4px solid '
                 f"#d4af37;padding-left:10px;margin:28px 0 12px;\">付费应用限时免费（{len(paid)} 款）</h2>")
        h.append('<p style="color:#444444;font-size:15px;">'
                 "点链接进 App Store 点“获取”就行。领的时候只点“获取”，不要买任何内购。</p>")
        html_paid_groups = group_by_category(paid)
        if len(html_paid_groups) >= 2:
            for cat, apps in html_paid_groups:
                h.append('<h3 style="font-size:16px;color:#222222;margin:20px 0 12px;">'
                         f"{html.escape(cat)}（{len(apps)} 款）</h3>")
                for i, a in enumerate(apps, 1):
                    h += _wechat_html_paid_card(a, i, languages, asset_dir, ymd)
        else:
            for i, a in enumerate(paid, 1):
                h += _wechat_html_paid_card(a, i, languages, asset_dir, ymd)
    if iaps:
        h.append('<h2 style="font-size:18px;color:#222222;border-left:4px solid '
                 f"#d4af37;padding-left:10px;margin:28px 0 12px;\">终身内购 0 元兑换（{len(iaps)} 个）</h2>")
        h.append('<p style="color:#444444;font-size:15px;">'
                 "这几个不是商店里直接降价到 0 元，而是开发者发的公开兑换码："
                 "点下面的兑换链接直接进 App Store 兑。每个兑换码一个 Apple "
                 "账号只能用一次，都是终身解锁、不是订阅，不会续费。</p>")
        h.append('<p style="color:#444444;font-size:15px;">'
                 "<strong style=\"color:#222222;\">怎么领：</strong>先装上对应的免费 App，"
                 "再点该款下面的兑换链接，自动跳到 App Store 兑换页确认就行。"
                 "不用绑卡，没有试用期。没有兑换链接的款，暂时只能先装 App，"
                 "等开发者放出公开码。</p>")
        html_iap_groups = group_by_category(iaps)
        if len(html_iap_groups) >= 2:
            for cat, apps in html_iap_groups:
                h.append('<h3 style="font-size:16px;color:#222222;margin:20px 0 12px;">'
                         f"{html.escape(cat)}（{len(apps)} 个）</h3>")
                for i, a in enumerate(apps, 1):
                    h += _wechat_html_iap_card(a, i, languages, asset_dir, ymd)
        else:
            for i, a in enumerate(iaps, 1):
                h += _wechat_html_iap_card(a, i, languages, asset_dir, ymd)
    h.append('<hr style="border:none;border-top:1px solid #eeeeee;margin:28px 0 12px;">')
    h.append('<p style="color:#999999;font-size:13px;text-align:center;">'
             "限免结束时间苹果不公布，一般 1–3 天，尽快领。</p>")
    h.append("</div></body></html>")
    path = os.path.join(DATA_DIR, date, "wechat.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(h))
    print(f"  wechat.html -> {path}")
    return path


# ---------------- main ----------------

def load_posted():
    """{app_id: date} of apps posted in the past (for 7-day dedup)."""
    p = os.path.join(DATA_DIR, "posted.json")
    if os.path.isfile(p):
        with open(p) as f:
            return {int(k): v for k, v in json.load(f).items()}
    return {}


def save_posted(posted):
    with open(os.path.join(DATA_DIR, "posted.json"), "w") as f:
        json.dump({str(k): v for k, v in posted.items()}, f, indent=1)


def pick_featured(paid):
    """Top paid apps for the "今日极力推荐" text and the cover icons.

    Chinese-only: only apps with a ZH localization (languageCodesISO2A
    contains 'ZH' — checked against the whole list, ZH sometimes
    repeats or sits late in it) are recommended, ordered by rating
    desc, at most 4. When fewer than 4 apps have ZH, the list is
    shorter — English-only apps are never used to fill the remainder.
    An empty list (no Chinese app that day) means no recommendation
    section that day; callers must handle it (write_post omits the
    section, the tg_post cover caption omits the line)."""
    return [a for a in sorted(
        paid, key=lambda a: a["rating"] or 0, reverse=True)
        if a.get("has_zh")][:4]


def pick_cover_icons(paid, iaps, languages, asset_dir):
    """Icon files for the cover, in priority order.

    1. featured (Chinese-only paid, at most 4) — the normal case.
    2. When featured is empty, the top at most 4 Chinese apps of the
       day (paid + IAPs with a ZH localization, by rating desc).
    3. [] when the day has no Chinese app at all — make_cover then
       draws the decorative fallback instead of blank space.
    English-only apps never appear on the cover."""
    featured = pick_featured(paid)
    if featured:
        return [os.path.join(asset_dir, f"{a['id']}.jpg") for a in featured]
    zh = []
    for a in paid:
        if a.get("has_zh"):
            zh.append((a.get("rating") or 0,
                       os.path.join(asset_dir, f"{a['id']}.jpg")))
    for a in iaps:
        if "ZH" in (languages.get(str(a["id"])) or []):
            zh.append((a.get("rating") or 0,
                       os.path.join(asset_dir, "iap", f"{a['id']}.jpg")))
    zh.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in zh[:4]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="generate + build only; skip deploy and Telegram")
    ap.add_argument("--skip-deploy", action="store_true")
    ap.add_argument("--skip-telegram", action="store_true")
    args = ap.parse_args()
    date = args.date or datetime.date.today().isoformat()
    ymd = date.replace("-", "")
    dry = args.dry_run
    print(f"== free-apps pipeline {date} (dry-run={dry}) ==")

    posted = load_posted()
    cutoff = (datetime.date.fromisoformat(date)
              - datetime.timedelta(days=7)).isoformat()

    # 1. scrape
    print("-- scrape --")
    candidates = sc.scrape_all()
    promos = sc.scrape_apphunt()
    print(f"candidates: {len(candidates)}, promos: {len(promos)}")

    # 1b. AppRaven cross-check — discovery. The AppRaven FREE list
    # (website's public GetAppsOnSale, rareOnly=False, no login, no Pro)
    # is fetched once; apps that went free in the last 48h and that no
    # other source caught are appended as candidates so they flow through
    # the same iTunes verification below. The same sale map is reused in
    # step 2b to verify each kept app's price history.
    appraven_sale, appraven_recent = {}, []
    try:
        appraven_sale, appraven_recent = sc.appraven_sale_list()
    except Exception as e:
        print(f"  [appraven-xcheck] sale list error: {e}; cross-check "
              f"skipped (fail-open)")
    cand_ids = {c["id"] for c in candidates}
    xcheck_added = 0
    for app_id in appraven_recent:
        if app_id not in cand_ids:
            sale = appraven_sale.get(app_id, {})
            candidates.append({
                "id": app_id,
                "name": sale.get("title", ""),
                "source": "appraven-xcheck",
            })
            cand_ids.add(app_id)
            xcheck_added += 1
    print(f"  [appraven-xcheck] added {xcheck_added} app(s) from the "
          f"AppRaven free list that other sources missed")

    # 2. verify + enrich paid apps
    print("-- verify paid apps --")
    paid, languages, apps_data = [], {}, {}
    for c in candidates:
        app_id = c["id"]
        if posted.get(app_id, "") >= cutoff:
            continue  # posted within the last 7 days
        rec = lookup(app_id)
        if not rec:
            print(f"  skip {app_id}: not in US store")
            continue
        if rec.get("price", 99) != 0:
            continue  # back to paid
        iap = has_iap(app_id)
        if iap is not False:
            print(f"  skip {app_id} {rec.get('trackName')}: "
                  f"has IAP (check={iap})")
            continue
        rating = rec.get("averageUserRating") or 0
        rcount = rec.get("userRatingCount") or 0
        if rating < 3.0 or (rating < 3.5 and rcount >= 20):
            print(f"  skip {app_id} {rec.get('trackName')}: "
                  f"low rating {rating} ({rcount})")
            continue
        price = c.get("price_usd")
        if price is None and c.get("price_cny"):
            price = cny_to_usd(c["price_cny"])
        devs, min_tvos = devices_for_app(rec, app_id)
        paid.append({
            "id": app_id,
            "name": rec.get("trackName", c["name"]),
            "price_usd": price,
            "rating": rating,
            "rating_count": rcount,
            "devices": devs,
            "min_os": rec.get("minimumOsVersion", "?"),
            "min_tvos": min_tvos,
            "size_bytes": rec.get("fileSizeBytes"),
            "genre": rec.get("primaryGenreName", ""),
            "category": category_zh(rec.get("primaryGenreName", "")),
            "has_zh": "ZH" in (rec.get("languageCodesISO2A") or []),
            "intro": chinese_intro(app_id, rec),
            "icon_url": rec.get("artworkUrl512", ""),
            "shots": (rec.get("screenshotUrls") or [])[:4],
        })
        languages[str(app_id)] = rec.get("languageCodesISO2A", [])
        apps_data[str(app_id)] = rec
        time.sleep(0.3)
        if len(paid) >= 15:
            break
    paid.sort(key=lambda a: ((a["price_usd"] or 0), a["rating"],
                             a["rating_count"]), reverse=True)
    print(f"paid apps kept: {len(paid)}")

    # 2b. AppRaven cross-check — price-history verification. For every
    # kept paid app that AppRaven tracks, its price history is checked:
    # "confirmed" (a DROP to tier 0) keeps it; "always_free" (launched
    # free, never paid) is a false positive and is dropped; "unknown"
    # (not in AppRaven's database, call failed, or inconclusive history)
    # keeps it — fail-open, never block on missing data. Apps AppRaven
    # does not list at all are kept and logged as uncorroborated.
    xcheck_confirmed = xcheck_blocked = xcheck_unknown = xcheck_nolist = 0
    kept_paid = []
    for a in paid:
        sale = appraven_sale.get(a["id"])
        if not sale:
            xcheck_nolist += 1
            kept_paid.append(a)
            continue
        verdict = "unknown"
        try:
            verdict = sc.appraven_price_verdict(sale.get("internal_id"))
        except Exception as e:
            print(f"  [appraven-xcheck] verdict error for {a['id']}: {e}")
        if verdict == "always_free":
            xcheck_blocked += 1
            print(f"  [appraven-xcheck] BLOCKED {a['name']} ({a['id']}): "
                  f"always free per AppRaven price history "
                  f"(launched free, never paid)")
            continue
        if verdict == "confirmed":
            xcheck_confirmed += 1
        else:
            xcheck_unknown += 1
        kept_paid.append(a)
        time.sleep(0.2)
    if xcheck_blocked:
        paid = kept_paid
        print(f"paid apps after cross-check: {len(paid)} "
              f"(blocked {xcheck_blocked})")
    print(f"  [appraven-xcheck] verified: confirmed={xcheck_confirmed} "
          f"blocked={xcheck_blocked} unknown={xcheck_unknown} "
          f"not-in-appraven-list={xcheck_nolist}")

    # 3. enrich IAP promos
    print("-- verify IAP promos --")
    # Public codes first: oodata scrape + curated file. AppHunt promos
    # (discovery only) add candidates without a public code — those are
    # listed with just their App Store link, never an AppHunt link.
    oodata_map = {c["id"]: c for c in sc.scrape_oodata()}
    curated = rc.load_public_codes()
    unlock_map = {p["id"]: p for p in promos}
    iap_candidates = []  # (app_id, display_name, unlock)
    for app_id, c in oodata_map.items():
        p = unlock_map.get(app_id, {})
        iap_candidates.append(
            (app_id, p.get("name") or "", p.get("unlock") or ""))
    for app_id in curated:
        if app_id not in oodata_map and app_id not in unlock_map:
            iap_candidates.append((app_id, "", ""))
    for p in promos:
        if p["id"] not in oodata_map and p["id"] not in curated:
            iap_candidates.append((p["id"], p["name"], p.get("unlock") or ""))
    iaps = []
    for app_id, disp_name, unlock in iap_candidates:
        rec = lookup(app_id)
        if not rec:
            continue
        lst = iap_list(app_id)
        if not lst:
            print(f"  skip promo {app_id}: no IAP list on store page")
            continue
        # match the promo IAP by name (from AppHunt unlock text), else priciest
        iap_name, iap_price = None, None
        m = re.search(r"unlocks?\s+([A-Z][\w ]*?)\s+for good", unlock, re.I)
        want = m.group(1).strip() if m else ""
        for n, pr in lst:
            if want and want.lower() in n.lower():
                iap_name, iap_price = n, pr
                break
        if iap_name is None:
            iap_name, iap_price = max(lst, key=lambda x: x[1])
        # Public custom offer code? Only a public Apple redeem link is
        # ever published; no AppHunt links, never a guessed code/URL.
        code, code_src = rc.find_public_code(
            app_id, rec.get("trackName", ""), rec.get("sellerUrl", ""),
            curated=curated,
            oodata={k: {"code": v["code"], "source": v["source"]}
                    for k, v in oodata_map.items()})
        redeem_url = rc.build_redeem_url(app_id, code) if code else ""
        if code:
            print(f"  promo {app_id} {rec.get('trackName')}: public code "
                  f"from {code_src}")
        devs, min_tvos = devices_for_app(rec, app_id)
        iaps.append({
            "id": app_id,
            "name": disp_name or rec.get("trackName", ""),
            "iap_name": iap_name,
            "iap_price": iap_price,
            "redeem_url": redeem_url,
            "redeem_code": code,  # raw public code, for xiaohongshu
            "unlock": unlock or f"解锁{iap_name}终身版。",
            "rating": rec.get("averageUserRating") or 0,
            "rating_count": rec.get("userRatingCount") or 0,
            "devices": devs,
            "min_os": rec.get("minimumOsVersion", "?"),
            "min_tvos": min_tvos,
            "size_bytes": rec.get("fileSizeBytes"),
            "genre": rec.get("primaryGenreName", ""),
            "category": category_zh(rec.get("primaryGenreName", "")),
            "intro": chinese_intro(app_id, rec),
            "icon_url": rec.get("artworkUrl512", ""),
            "shots": (rec.get("screenshotUrls") or [])[:4],
        })
        languages[str(app_id)] = rec.get("languageCodesISO2A", [])
        apps_data[str(app_id)] = rec
        time.sleep(0.3)
        if len(iaps) >= 8:
            break
    print(f"iap promos kept: {len(iaps)}")

    if not paid and not iaps:
        print("nothing to post today")
        return 0

    # 4. download assets
    print("-- download assets --")
    asset_dir = os.path.join(ASSETS_DIR, f"free-apps-{ymd}")
    os.makedirs(os.path.join(asset_dir, "shots"), exist_ok=True)
    os.makedirs(os.path.join(asset_dir, "iap"), exist_ok=True)
    os.makedirs(os.path.join(asset_dir, "iap-shots"), exist_ok=True)
    for a in paid:
        if a["icon_url"]:
            download_image(a["icon_url"],
                           os.path.join(asset_dir, f"{a['id']}.jpg"))
        for i, s in enumerate(a["shots"], 1):
            download_image(s, os.path.join(
                asset_dir, "shots", f"{a['id']}-{i}.jpg"))
    for a in iaps:
        if a["icon_url"]:
            download_image(a["icon_url"], os.path.join(
                asset_dir, "iap", f"{a['id']}.jpg"))
        for i, s in enumerate(a["shots"], 1):
            download_image(s, os.path.join(
                asset_dir, "iap-shots", f"{a['id']}-{i}.jpg"))

    # Channel banners: stitch each app's screenshots (up to 4) into one
    # wide banner-<id>.jpg for the Telegram post (same banner is the blog
    # header image for the app; see write_post).
    for a in paid:
        shot_files = [os.path.join(asset_dir, "shots", f"{a['id']}-{i}.jpg")
                      for i in range(1, len(a["shots"]) + 1)]
        shot_files = [p for p in shot_files if os.path.isfile(p)]
        try:
            build_banner(shot_files,
                         os.path.join(asset_dir, f"banner-{a['id']}.jpg"))
        except Exception as e:
            print(f"  banner failed for {a['id']}: {e}")
    for a in iaps:
        shot_files = [os.path.join(asset_dir, "iap-shots",
                                   f"{a['id']}-{i}.jpg")
                      for i in range(1, len(a["shots"]) + 1)]
        shot_files = [p for p in shot_files if os.path.isfile(p)]
        try:
            build_banner(shot_files,
                         os.path.join(asset_dir, f"banner-{a['id']}.jpg"))
        except Exception as e:
            print(f"  banner failed for {a['id']}: {e}")

    # 5. featured + cover (featured is Chinese-only, at most 4: see
    # pick_featured; the same list drives both the recommendation text
    # and the cover icons, so one change covers both).
    # Cover icons: featured when there are any; when featured is empty
    # the day's Chinese apps fill the cover (pick_cover_icons); when
    # the day has no Chinese app at all make_cover draws a decorative
    # fallback — the cover is never 70% blank dark space.
    featured = pick_featured(paid)
    make_cover(pick_cover_icons(paid, iaps, languages, asset_dir),
               os.path.join(asset_dir, "cover.jpg"), date, len(paid),
               n_iaps=len(iaps))

    # 6. write post + data files
    write_post(date, paid, iaps, featured, asset_dir, languages)
    day_data = os.path.join(DATA_DIR, date)
    os.makedirs(day_data, exist_ok=True)
    with open(os.path.join(day_data, "apps.json"), "w") as f:
        json.dump(apps_data, f, ensure_ascii=False, indent=1)
    with open(os.path.join(day_data, "languages.json"), "w") as f:
        json.dump(languages, f, ensure_ascii=False, indent=1)
    # WeChat article (Markdown + paste-ready HTML) and Xiaohongshu note.
    # File generation only — deploy and Telegram are untouched by them.
    write_wechat(date, paid, iaps, featured, languages, asset_dir)
    write_wechat_html(date, paid, iaps, featured, languages, asset_dir)
    write_xiaohongshu(date, paid, iaps, asset_dir)
    for a in paid + iaps:
        posted[a["id"]] = date
    # A dry run must not pollute the dedup record: tomorrow's real run
    # would otherwise skip every app this test run touched.
    if not dry:
        save_posted(posted)

    # 7. build
    print("-- build --")
    r = os.system(f"cd {ROOT} && python3 build.py")
    if r != 0:
        print("build.py failed")
        return 1

    # 8. deploy
    if not dry and not args.skip_deploy:
        print("-- deploy --")
        token = os.environ.get("CLOUDFLARE_API_TOKEN")
        if not token:
            print("CLOUDFLARE_API_TOKEN not set; deploy skipped "
                  "(set the secret to enable)")
        else:
            r = os.system(f"cd {ROOT} && python3 deploy.py")
            if r != 0:
                print("deploy.py failed (continuing to Telegram)")
    else:
        print("-- deploy skipped --")

    # 9. telegram
    if not dry and not args.skip_telegram:
        print("-- telegram --")
        r = os.system(
            f"cd {ROOT} && python3 automation/tg_post.py --date {date}")
        if r != 0:
            print("tg_post.py failed")
            return 1
    else:
        print("-- telegram skipped --")
    print("== done ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
