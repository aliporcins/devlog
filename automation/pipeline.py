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
  iTunes Lookup has no IAP field).
- Writes the blog post (posts/<date>-free-apps.md), downloads icons +
  up to 4 screenshots per app (first 2 in the blog carousel, all stitched
  into a wide channel banner banner-<id>.jpg), writes languages.json +
  apps.json, builds a PIL cover from the featured icons, runs build.py,
  deploys via wrangler (needs CLOUDFLARE_API_TOKEN env), then posts to
  Telegram via tg_post.py.
- --dry-run: generate everything but skip deploy and Telegram (writes files
  under a test date directory; safe to run any time).
- Never invents a free-app end date; never logs in to Apple ID; never buys.

Repo root is the parent of this script's directory (the devlog checkout).
"""
import argparse
import datetime
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


def store_page(app_id):
    """Fetch the US App Store page HTML (follows the slug redirect)."""
    url = f"https://apps.apple.com/us/app/id{app_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept-Language": "en-US"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  [store] {app_id} page failed: {e}")
        return ""


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

DEVICE_MAP = [("iPhone", "iPhone"), ("iPad", "iPad"), ("iPod", "iPod touch"),
              ("Mac", "Mac"), ("Watch", "Apple Watch"), ("TV", "Apple TV")]
DEVICE_ORDER = ["iPhone", "iPad", "iPod touch", "Mac", "Apple TV",
                "Apple Watch"]


def format_devices(record):
    seen = []
    for d in record.get("supportedDevices", []):
        for prefix, label in DEVICE_MAP:
            if d.startswith(prefix) and label not in seen:
                seen.append(label)
    # canonical order (matches the live posting script's devices_for)
    return " / ".join([x for x in DEVICE_ORDER if x in seen]) if seen else ""


def first_sentence(text, max_len=70):
    """First sentence of a description, capped at ~max_len chars."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"[。！？\n]", text)
    for p in parts:
        p = p.strip()
        if len(p) >= 8:
            if len(p) > max_len:
                p = p[:max_len].rstrip() + "…"
            return p
    return text[:max_len]


def chinese_intro(app_id, us_record):
    """One-line Chinese intro: CN description first sentence, else US."""
    cn = lookup(app_id, country="CN")
    if cn and cn.get("description"):
        s = first_sentence(cn["description"])
        if s and any("\u4e00" <= ch <= "\u9fff" for ch in s):
            return s
    if us_record.get("description"):
        s = first_sentence(us_record["description"])
        if s:
            return s
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

def make_cover(icon_paths, out_path, date_str, n_apps):
    """1200x630 dark cover: featured icons + title text."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), (18, 18, 24))
    d = ImageDraw.Draw(img)
    # subtle gold accent bar
    d.rectangle([0, 0, W, 10], fill=(212, 175, 55))
    try:
        font_big = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
        font_small = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
    except Exception:
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()
    d.text((60, 60), "今日限免", font=font_big, fill=(245, 245, 245))
    d.text((60, 150), f"{date_str} · {n_apps} 款完全免费",
           font=font_small, fill=(200, 200, 210))
    x = 60
    for p in icon_paths[:3]:
        try:
            icon = Image.open(p).convert("RGB").resize((220, 220))
        except Exception:
            continue
        img.paste(icon, (x, 300))
        x += 260
    img.save(out_path, "JPEG", quality=88)
    print(f"  cover -> {out_path}")


# ---------------- blog post ----------------

def esc(s):
    return s.replace("|", "｜")


def write_post(date, paid, iaps, featured, asset_dir):
    """Write posts/<date>-free-apps.md in the 2026-11-23 format."""
    ymd = date.replace("-", "")
    slug = f"free-apps-{ymd}"
    total_paid = sum(a["price_usd"] or 0 for a in paid)
    total_iap = sum(a["iap_price"] or 0 for a in iaps)
    title = (f"今日限免 App（{date}）：{len(paid)} 款付费应用免费领"
             f"＋{len(iaps)} 个终身内购 0 元兑")
    excerpt = (f"今天 {len(paid)} 款付费 App 限时免费，原价加起来约 "
               f"{total_paid:.0f} 美元；另有 {len(iaps)} 个终身内购可用兑换码 "
               f"0 元领，原价加起来约 {total_iap:.0f} 美元。点链接进 App Store "
               f"点“获取”就行，限免随时结束，看到就领。")
    lines = [
        "---",
        f"title: {title}",
        f"date: {date}",
        "tag: 接单学习",
        "tagkey: plan",
        f"slug: {slug}",
        f"cover: free-apps-{ymd}/cover.jpg",
        f"excerpt: {excerpt}",
        "---",
        "",
        (f"今天 {len(paid)} 款付费 App 限时免费，原价加起来约 "
         f"{total_paid:.0f} 美元；另外还有 {len(iaps)} 个终身内购可用兑换码 "
         f"0 元领，原价加起来约 {total_iap:.0f} 美元。都是今天刚确认的，"
         f"限免随时可能结束，看到喜欢的就领。"),
        "",
        "## 今日极力推荐",
        "",
    ]
    for i, a in enumerate(featured, 1):
        lines.append(
            f"{i}. **{a['name']}** — 评分 {a['rating']:.1f}，原价 "
            f"${a['price_usd']:.2f}，{a['intro']}")
    lines += ["", "", f"## 付费应用限时免费（{len(paid)} 款）", "",
              "点链接进 App Store 点“获取”就行。领的时候只点“获取”，不要买任何内购。",
              ""]
    for i, a in enumerate(paid, 1):
        # Header image: the same wide banner as the channel post; fall
        # back to the icon when the banner could not be built.
        header = (f"banner-{a['id']}.jpg"
                  if os.path.isfile(os.path.join(
                      asset_dir, f"banner-{a['id']}.jpg"))
                  else f"{a['id']}.jpg")
        lines += [
            f"### {i}. {a['name']}",
            "",
            f"![{a['name']}](../assets/free-apps-{ymd}/{header})",
            "",
            f"- **原价**：${a['price_usd']:.2f}，现在免费" if a["price_usd"]
            else "- **原价**：付费应用，现在免费",
            f"- **评分**：★{a['rating']:.1f} ({a['rating_count']:,})",
            f"- **支持设备**：{a['devices']}",
            f"- **最低系统**：iOS {a['min_os']}",
            f"- **干什么的**：{a['intro']}",
            f"- **领取**：[在 App Store 打开](https://apps.apple.com/us/app/id{a['id']})",
            "",
            "!carousel",
            f"![{a['name']} 预览 1](../assets/free-apps-{ymd}/shots/{a['id']}-1.jpg)",
            f"![{a['name']} 预览 2](../assets/free-apps-{ymd}/shots/{a['id']}-2.jpg)",
            "",
        ]
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
        for i, a in enumerate(iaps, 1):
            header = (f"banner-{a['id']}.jpg"
                      if os.path.isfile(os.path.join(
                          asset_dir, f"banner-{a['id']}.jpg"))
                      else f"iap/{a['id']}.jpg")
            section_lines = [
                f"### {i}. {a['name']}",
                "",
                f"![{a['name']}](../assets/free-apps-{ymd}/{header})",
                "",
                f"- **内购**：{a['iap_name']}",
                f"- **原价**：${a['iap_price']:.2f}，兑换码 0 元领" if a.get("iap_price")
                else "- **原价**：兑换码 0 元领",
                (f"- **评分**：★{a['rating']:.1f} ({a['rating_count']:,})"
                 if a.get("rating") else "- **评分**：暂无评分"),
                f"- **支持设备**：{a['devices']}",
                f"- **干什么的**：{a['intro']}",
                f"- **解锁内容**：{a['unlock']}",
                f"- **最低系统**：iOS {a['min_os']}",
            ]
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
            lines += section_lines
    lines += ["---", "", "限免结束时间苹果不公布，一般 1–3 天，尽快领。", ""]
    path = os.path.join(POSTS_DIR, f"{date}-free-apps.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  post -> {path}")
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
        paid.append({
            "id": app_id,
            "name": rec.get("trackName", c["name"]),
            "price_usd": price,
            "rating": rating,
            "rating_count": rcount,
            "devices": format_devices(rec),
            "min_os": rec.get("minimumOsVersion", "?"),
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
        iaps.append({
            "id": app_id,
            "name": disp_name or rec.get("trackName", ""),
            "iap_name": iap_name,
            "iap_price": iap_price,
            "redeem_url": redeem_url,
            "unlock": unlock or f"解锁{iap_name}终身版。",
            "rating": rec.get("averageUserRating") or 0,
            "rating_count": rec.get("userRatingCount") or 0,
            "devices": format_devices(rec),
            "min_os": rec.get("minimumOsVersion", "?"),
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

    # 5. featured + cover
    featured = sorted(
        paid, key=lambda a: ((a["price_usd"] or 0), a["rating"]),
        reverse=True)[:3]
    make_cover([os.path.join(asset_dir, f"{a['id']}.jpg") for a in featured],
               os.path.join(asset_dir, "cover.jpg"), date, len(paid))

    # 6. write post + data files
    write_post(date, paid, iaps, featured, asset_dir)
    day_data = os.path.join(DATA_DIR, date)
    os.makedirs(day_data, exist_ok=True)
    with open(os.path.join(day_data, "apps.json"), "w") as f:
        json.dump(apps_data, f, ensure_ascii=False, indent=1)
    with open(os.path.join(day_data, "languages.json"), "w") as f:
        json.dump(languages, f, ensure_ascii=False, indent=1)
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
