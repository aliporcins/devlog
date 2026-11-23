#!/usr/bin/env python3
"""Scrapers for daily iOS free-app sources.

Sources (all verified 2026-11-23):
- Mergeek  https://mergeek.com/free/apps  (primary, domestic)
  Page lists app names (aria-label / data-caption) + internal codes; NO App
  Store IDs in the HTML, so IDs are resolved via the iTunes Search API by
  exact name match. Requires full browser headers or the server returns a
  Ruby template error (403).
- GoFans  https://gofans.cn  (domestic)
  Homepage lists /app/<uuid> links; each detail page embeds the App Store
  link (escaped JSON: apps.apple.com/cn/app/.../id<id>).
- AppRaven (ex-AppSliced)  https://appraven.net/appraven/graphql
  GraphQL GetAppsOnSale returns ITunesId, title, rating, hasInAppPurchases.
- 360-reader  https://360-reader.com/paid-iphone-apps-gone-free/
  Plain HTML with direct apps.apple.com/us/app/.../id<id> links.
- oodata.net  https://apps.oodata.net/search/result?q=%23IAP
  Aggregator of developer-published PUBLIC custom offer codes; the IAP
  list page embeds apps.apple.com/redeem?id=<id>&code=<code> links.
- AppHunt  https://apphunt.app/promos  (DISCOVERY ONLY)
  Day cards carry the app ID (clips/<id>-sm.jpg, api/icons/<id>) and a
  /app/<slug> detail page with unlock text. No AppHunt links, codes, or
  code counts are published anywhere (user rule 2026-11-23).

Every function returns a list of dicts with at least {'id': int, 'name': str,
'source': str}. Network access uses only stdlib urllib; no API keys needed.
"""
import datetime
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def fetch(url, headers=None, data=None, timeout=30, tries=3):
    """GET (or POST when data is given) with browser headers and retries."""
    h = dict(BASE_HEADERS)
    if headers:
        h.update(headers)
    last_err = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=h,
                                         method="POST" if data else "GET")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code} {url}"
            if e.code in (403, 404):
                break
            time.sleep(2 * (attempt + 1))
        except Exception as e:  # timeout / connection reset
            last_err = f"{type(e).__name__} {url}: {e}"
            time.sleep(2 * (attempt + 1))
    print(f"  [scrape] fetch failed: {last_err}")
    return ""


def itunes_search_id(name):
    """Resolve an App Store ID by exact app-name match via iTunes Search API.

    Tries the US store first, then the CN store (Mergeek lists Chinese
    display names; the ID is the same across stores). Returns the trackId
    of the exact-name match (preferring a free app with the most ratings),
    or None.
    """
    for country in ("US", "CN"):
        q = urllib.parse.quote(name)
        url = (f"https://itunes.apple.com/search?term={q}&entity=software"
               f"&country={country}&limit=10")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode())
        except Exception as e:
            print(f"  [scrape] itunes search failed for {name!r}: {e}")
            return None
        exact = [x for x in d.get("results", [])
                 if x.get("trackName", "").strip().lower()
                 == name.strip().lower()]
        if exact:
            exact.sort(key=lambda x: (x.get("price", 99) == 0,
                                      x.get("userRatingCount", 0)),
                       reverse=True)
            return exact[0]["trackId"]
    return None


def scrape_mergeek(max_pages=2):
    """Mergeek free-apps list. Returns [{'id','name','source'}]."""
    out, seen = [], set()
    for page in range(1, max_pages + 1):
        url = f"https://mergeek.com/free/apps?page={page}" if page > 1 \
            else "https://mergeek.com/free/apps"
        html = fetch(url, headers={"Referer": "https://mergeek.com/"})
        if not html:
            continue
        names = set()
        for m in re.finditer(r'aria-label="([^"]+)"', html):
            names.add(m.group(1).strip())
        for m in re.finditer(r'data-caption="([^"]+)"', html):
            names.add(m.group(1).strip())
        # Original CNY price per app: "~~¥38~~ ¥0" near the app name
        cny = {}
        for m in re.finditer(
                r'aria-label="([^"]+)"[^>]*>.*?~~¥([\d.]+)~~', html, re.S):
            cny[m.group(1).strip()] = float(m.group(2))
        for raw in sorted(names):
            if not raw or raw in seen:
                continue
            # Clean the label: real app entries carry a price suffix
            # ("，原价 68 元，现价 0 元" / "，会员优惠价 19.0 元，查看优惠");
            # strip it to get the bare app name for the iTunes search.
            name = re.split(r"，(?:原价|会员优惠价|查看优惠)", raw)[0].strip()
            # Pagination / navigation labels, not apps
            if re.match(r"^第\s*\d+\s*页$", name):
                continue
            # UI chrome labels (not apps): "关闭反馈", "刷新二维码",
            # "前往宝石兑换查看 X", "显示或隐藏密码", "应用列表分页",
            # "移动端主导航", "精选活动与应用福利", "广告", "消息"
            if (name in ("广告", "消息")
                    or name.startswith("显示或隐藏")
                    or any(w in name for w in
                           ("查看", "兑换", "反馈", "二维码", "导航",
                            "分页", "福利"))):
                continue
            seen.add(raw)
            app_id = itunes_search_id(name)
            if app_id:
                out.append({"id": app_id, "name": name, "source": "mergeek",
                            "price_cny": cny.get(raw)})
            else:
                print(f"  [mergeek] no exact iTunes match for {name!r}, skipped")
        time.sleep(1)
    print(f"  [mergeek] {len(out)} apps")
    return out


def scrape_gofans(max_apps=20):
    """GoFans homepage + detail pages. Returns [{'id','name','source'}]."""
    out = []
    html = fetch("https://gofans.cn/")
    if not html:
        return out
    # The app name sits in <a href="/app/<uuid>"><strong class="title">NAME</strong></a>
    cards = re.findall(
        r'href="/app/([0-9a-f-]{36})"[^>]*>\s*<strong[^>]*>([^<]+)</strong>',
        html)
    seen_uuids = set()
    for uuid, name in cards:
        if uuid in seen_uuids:
            continue
        seen_uuids.add(uuid)
        detail = fetch(f"https://gofans.cn/app/{uuid}")
        m = re.search(r"apps\.apple\.com\\u002Fcn\\u002Fapp\\u002F[^\\]*\\u002Fid(\d+)",
                      detail)
        if not m:
            m = re.search(r"apps\.apple\.com/cn/app/[^/\"']+/id(\d+)", detail)
        if m:
            out.append({"id": int(m.group(1)),
                        "name": name or f"gofans-{uuid[:8]}",
                        "source": "gofans"})
        time.sleep(0.5)
        if len(out) >= max_apps:
            break
    print(f"  [gofans] {len(out)} apps")
    return out


APPRAVEN_GQL = (
    "query GetAppsOnSale($rareOnly: Boolean!, $miniFilter: MiniFilterInput!, "
    "$page: Int!, $pageSize: Int!) { appsOnSale(rareOnly: $rareOnly, "
    "miniFilter: $miniFilter, page: $page, pageSize: $pageSize) { content { "
    "app { id ITunesId title priceTier rating ratingCount hasInAppPurchases } "
    "} hasNext } }")


def scrape_appraven(page_size=30):
    """AppRaven GraphQL appsOnSale. Returns [{'id','name','source',...}]."""
    out = []
    body = json.dumps({
        "operationName": "GetAppsOnSale",
        "variables": {"rareOnly": True, "miniFilter": {"ratingCount": 10},
                      "page": 0, "pageSize": page_size},
        "query": APPRAVEN_GQL,
    }).encode()
    raw = fetch("https://appraven.net/appraven/graphql",
                headers={"Content-Type": "application/json"}, data=body)
    if not raw:
        return out
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        print("  [appraven] bad JSON")
        return out
    for item in d.get("data", {}).get("appsOnSale", {}).get("content", []):
        app = item.get("app") or {}
        if app.get("ITunesId"):
            out.append({
                "id": int(app["ITunesId"]),
                "name": app.get("title", ""),
                "source": "appraven",
                "rating": app.get("rating"),
                "rating_count": app.get("ratingCount"),
                "has_iap": app.get("hasInAppPurchases"),
            })
    print(f"  [appraven] {len(out)} apps")
    return out


# ---------------- AppRaven cross-check ----------------
# The AppRaven FREE version's daily free list is the website's own public
# sale list (appraven.net, no login, no Pro): the same GetAppsOnSale
# GraphQL the site itself calls. rareOnly=False = every app currently on
# sale (not just the "rare" subset the discovery source uses), paginated
# so the whole list is covered. lastActivity carries the most recent
# price change, so a DROP to tier 0 within the last 48h marks a genuinely
# new free deal; older/still-paid entries are not "today's" deals.
# GetAppDetail (same public endpoint) returns the full price history
# (activityList: every DROP/RISE with priceTierFrom/priceTierTo, plus the
# RELEASE event with the launch price tier). That history is what the
# cross-check verifies against: a real deal has a DROP to tier 0; an app
# that launched free (RELEASE tier 0) and never had a price is a
# perennially-free false positive. No Pro data, no unlock, no App API.
APPRAVEN_SALE_GQL = (
    "query GetAppsOnSale($rareOnly: Boolean!, $miniFilter: MiniFilterInput!, "
    "$page: Int!, $pageSize: Int!) { appsOnSale(rareOnly: $rareOnly, "
    "miniFilter: $miniFilter, page: $page, pageSize: $pageSize) { content { "
    "app { id ITunesId title priceTier rating ratingCount hasInAppPurchases "
    "lastActivity { timestamp "
    "... on AppActivityPriceChange { priceChangeType: type priceTierFrom } "
    "... on AppActivityAvailability { availabilityChangeType: type } "
    "... on AppActivityUpdate { versionTo } } } "
    "} hasNext } }")
APPRAVEN_DETAIL_GQL = (
    "query GetAppDetail($id: ID!) { app(id: $id) { id ITunesId title "
    "priceTier activityList { id timestamp "
    "... on AppActivityPriceChange { priceChangeType: type priceTierFrom "
    "priceTierTo } "
    "... on AppActivityAvailability { availabilityChangeType: type priceTier } "
    "... on AppActivityUpdate { versionFrom versionTo } } } }")
# How far back a price DROP counts as a "new" free deal (hours).
APPRAVEN_RECENT_HOURS = 48
# Bound the sale-list pagination so a huge catalog cannot stall the run.
APPRAVEN_MAX_PAGES = 8


def _appraven_gql(query, variables, op):
    """One AppRaven GraphQL call (website's public endpoint, no auth).
    Returns the parsed JSON dict, or None on any failure."""
    body = json.dumps({"operationName": op, "variables": variables,
                       "query": query}).encode()
    raw = fetch("https://appraven.net/appraven/graphql",
                headers={"Content-Type": "application/json"}, data=body)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _parse_ts(ts):
    """ISO-8601 timestamp (with Z or offset) -> aware datetime, or None."""
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(
            ts.replace("Z", "+00:00"))
    except Exception:
        return None


def appraven_sale_list(max_pages=APPRAVEN_MAX_PAGES):
    """AppRaven free list (public GetAppsOnSale, rareOnly=False).

    Returns (sale, recent_free):
    - sale: {itunes_id: {"internal_id", "priceTier", "title", "last": {...}}}
      for every app on the sale list (paginated, capped at max_pages).
    - recent_free: [itunes_id, ...] that are currently free (tier 0) and
      whose last activity is a price DROP within APPRAVEN_RECENT_HOURS —
      i.e. genuinely new free deals, not apps that have been free for weeks.
    On any failure returns the partial (sale, recent_free) collected so
    far — a transient drop on a later page must not discard the pages
    already fetched. When nothing could be fetched at all it returns
    ({}, []), and the caller treats that as "no cross-check data" and
    keeps everything (fail-open)."""
    import datetime as _dt
    sale, recent_free = {}, []
    cutoff = (_dt.datetime.now(_dt.timezone.utc)
              - _dt.timedelta(hours=APPRAVEN_RECENT_HOURS))
    pages = 0
    for page in range(max_pages):
        d = _appraven_gql(APPRAVEN_SALE_GQL,
                          {"rareOnly": False,
                           "miniFilter": {"ratingCount": 10},
                           "page": page, "pageSize": 30},
                          "GetAppsOnSale")
        if not d:
            print("  [appraven-xcheck] sale list fetch failed "
                  f"(page {page}); keeping the {len(sale)} app(s) fetched "
                  f"so far")
            break
        node = (d.get("data") or {}).get("appsOnSale") or {}
        content = node.get("content") or []
        pages += 1
        for item in content:
            app = item.get("app") or {}
            itid = app.get("ITunesId")
            if not itid:
                continue
            itid = int(itid)
            last = app.get("lastActivity") or {}
            sale[itid] = {
                "internal_id": app.get("id"),
                "priceTier": app.get("priceTier"),
                "title": app.get("title", ""),
                "last": last,
            }
            if (app.get("priceTier") == 0
                    and last.get("priceChangeType") == "DROP"):
                ts = _parse_ts(last.get("timestamp"))
                if ts and ts >= cutoff:
                    recent_free.append(itid)
        if not node.get("hasNext"):
            break
        time.sleep(0.5)
    print(f"  [appraven-xcheck] sale list: {len(sale)} apps across "
          f"{pages} page(s); recent-free (tier 0 + DROP < "
          f"{APPRAVEN_RECENT_HOURS}h): {len(recent_free)}")
    return sale, recent_free


def appraven_price_verdict(internal_id):
    """Price-history verdict for one app (by AppRaven internal id).

    Returns one of:
    - "confirmed": activityList has a DROP with priceTierTo == 0 and
      priceTierFrom > 0 — the app really went from paid to free.
    - "always_free": the app launched free (RELEASE availability with
      priceTier 0) and the whole history has no DROP to tier 0 — it was
      never paid, so listing it as "paid turned free" is a false positive.
    - "unknown": AppRaven has no record of the app, the call failed, or
      the history is inconclusive (e.g. truncated before the RELEASE).
      Callers keep the app on "unknown" (fail-open)."""
    if not internal_id:
        return "unknown"
    d = _appraven_gql(APPRAVEN_DETAIL_GQL, {"id": str(internal_id)},
                      "GetAppDetail")
    if not d:
        return "unknown"
    app = (d.get("data") or {}).get("app")
    if not app:
        return "unknown"
    acts = app.get("activityList") or []
    has_drop_to_free = False
    released_free = False
    for a in acts:
        if a.get("priceChangeType") == "DROP" and a.get("priceTierTo") == 0 \
                and (a.get("priceTierFrom") or 0) > 0:
            has_drop_to_free = True
        if a.get("availabilityChangeType") == "RELEASE" \
                and a.get("priceTier") == 0:
            released_free = True
    if has_drop_to_free:
        return "confirmed"
    if released_free:
        return "always_free"
    return "unknown"


def scrape_360reader():
    """360-reader daily free list. Returns [{'id','name','source','price_usd',
    'rating','rating_count'}] — prices come from the comparison table."""
    out, seen = [], set()
    html = fetch("https://360-reader.com/paid-iphone-apps-gone-free/")
    if not html:
        return out
    prices, ratings = {}, {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        m = re.search(r"id(\d+)", row)
        if not m:
            continue
        app_id = int(m.group(1))
        txt = re.sub(r"<[^>]+>", " ", row)
        txt = re.sub(r"\s+", " ", txt).strip()
        pm = re.search(r"\$([\d.]+)", txt)
        if pm and app_id not in prices:
            prices[app_id] = float(pm.group(1))
        rm = re.search(r"★\s*([\d.]+)\s*\(([\d,]+)\s*ratings?\)", txt)
        if rm:
            ratings[app_id] = (float(rm.group(1)),
                               int(rm.group(2).replace(",", "")))
    for m in re.finditer(
            r"apps\.apple\.com/us/app/([^/\"']+)/id(\d+)", html):
        app_id = int(m.group(2))
        if app_id in seen:
            continue
        seen.add(app_id)
        name = m.group(1).replace("-", " ").strip()
        entry = {"id": app_id, "name": name, "source": "360reader",
                 "price_usd": prices.get(app_id)}
        if app_id in ratings:
            entry["rating"], entry["rating_count"] = ratings[app_id]
        out.append(entry)
    print(f"  [360reader] {len(out)} apps")
    return out


def scrape_apphunt(max_cards=8):
    """AppHunt promos: today's lifetime deal + previous days still free.

    DISCOVERY ONLY: tells us which apps currently have a free lifetime
    IAP (and what the IAP unlocks). No AppHunt links, codes, or code
    counts are published anywhere (user rule 2026-11-23: only public
    direct Apple redeem links are posted). A promo with no public code
    is still listed, with just its App Store link.

    Returns [{'id','name','slug','source','unlock'}]. unlock comes from
    the /app/<slug> detail page.
    """
    out = []
    html = fetch("https://apphunt.app/promos")
    if not html:
        return out
    cards = re.findall(
        r'class="day-card" href="/app/([^"]+)".*?'
        r'<span class="day-name">([^<]+)</span>', html, re.S)
    for slug, name in cards[:max_cards]:
        # App ID from the card's clip/icon URL
        seg = html.split(f'href="/app/{slug}"', 1)
        app_id = None
        if len(seg) > 1:
            m = re.search(r"/(?:clips|api/icons)/(\d+)", seg[1][:3000])
            if m:
                app_id = int(m.group(1))
        if not app_id:
            continue
        detail = fetch(f"https://apphunt.app/app/{slug}")
        unlock = ""
        m = re.search(r"unlocks?\s+([^<.]{10,200})", detail, re.I)
        if m:
            unlock = m.group(1).strip()
        # Discard the generic boilerplate ("unlocks a one-time purchase, not
        # a subscription...") — it says nothing about what the IAP unlocks.
        # The pipeline falls back to "解锁<IAP名>终身版" in that case.
        if unlock.lower().startswith("a one-time purchase"):
            unlock = ""
        out.append({"id": app_id, "name": name.strip(), "slug": slug,
                    "source": "apphunt", "unlock": unlock})
        time.sleep(0.5)
    print(f"  [apphunt] {len(out)} promos")
    return out


def scrape_oodata():
    """oodata.net IAP list (apps.oodata.net/search/result?q=%23IAP) — an
    aggregator of developer-published PUBLIC custom offer codes.
    Returns [{'id','code','source'}] with the redeem code per app.
    Only href="...redeem..." attributes are parsed (the page's title
    attributes concatenate the code with following text, e.g. 'GPSPHOTOoO').
    First code per app wins when a post lists several.
    """
    out, seen = [], set()
    html = fetch("https://apps.oodata.net/search/result?q=%23IAP")
    if not html:
        return out
    # Pass 1: href="...redeem..." attributes — exact codes, any case.
    for m in re.finditer(
            r'href="https://apps\.apple\.com/redeem\?id=(\d+)&amp;code='
            r'([A-Za-z0-9_-]+)"', html):
        app_id, code = int(m.group(1)), m.group(2)
        if app_id in seen:
            continue
        seen.add(app_id)
        out.append({"id": app_id, "code": code, "source": "oodata"})
    # Pass 2: codes that only appear in a post's title attribute, where the
    # code runs into following text ("GPSPHOTOoO Links:"). Public codes
    # are uppercase by convention, so match uppercase only — the trailing
    # text ("oO", "https") does not get glued on. Only for apps not
    # already found in pass 1.
    for m in re.finditer(
            r'redeem\?(?:ctx=offercodes&)?id=(\d+)(?:&amp;|&)code='
            r'([A-Z0-9][A-Z0-9_-]{3,})', html):
        app_id, code = int(m.group(1)), m.group(2)
        if app_id in seen:
            continue
        seen.add(app_id)
        out.append({"id": app_id, "code": code, "source": "oodata"})
    print(f"  [oodata] {len(out)} public codes")
    return out


def scrape_all():
    """Run every paid-app source; returns deduped list (first source wins)."""
    seen, out = set(), []
    for fn in (scrape_mergeek, scrape_gofans, scrape_appraven, scrape_360reader):
        try:
            for a in fn():
                if a["id"] not in seen:
                    seen.add(a["id"])
                    out.append(a)
        except Exception as e:
            print(f"  [scrape] {fn.__name__} failed: {e}")
    return out


if __name__ == "__main__":
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which == "all":
        apps = scrape_all()
        print(f"total deduped: {len(apps)}")
        for a in apps[:20]:
            print(" ", a["id"], a["name"], f"({a['source']})")
    elif which == "apphunt":
        for a in scrape_apphunt():
            print(" ", a)
    elif which == "oodata":
        for a in scrape_oodata():
            print(" ", a)
    else:
        fn = {"mergeek": scrape_mergeek, "gofans": scrape_gofans,
              "appraven": scrape_appraven, "360": scrape_360reader}[which]
        for a in fn():
            print(" ", a["id"], a["name"])
