#!/usr/bin/env python3
"""Public Apple redeem links for lifetime IAPs.

A public redeem link is https://apps.apple.com/redeem?ctx=offercodes
&id=<App ID>&code=<public custom code> — a custom offer code the developer
created in App Store Connect and published openly (own site, social
media, promo channels). Opening it goes straight to the App Store redeem
page; no third-party login.

Sources, in priority order:
1. automation/data/public_codes.json — curated {app_id: {"code", "source"}}
   for codes found by research (e.g. SuperC / SUPERC2026).
2. oodata.net IAP list (scrape_oodata in scrape.py) — an aggregator of
   developer-published public codes, scraped fresh each run.
3. The developer's own website (sellerUrl from iTunes Lookup) — fetched
   and searched for an apps.apple.com/redeem link for this app.

Rules (user, 2026-11-23): only public direct redeem links are ever
published. AppHunt offer pages are NOT used. If no public code is found
for an IAP, the post lists the app with only its App Store link — never
guess or fabricate a code or URL.
"""
import json
import os
import re
import urllib.parse
import urllib.request

CURATED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "data", "public_codes.json")


def build_redeem_url(app_id, code):
    """Public Apple redeem link for a custom offer code."""
    q = urllib.parse.quote(str(code), safe="")
    return (f"https://apps.apple.com/redeem?ctx=offercodes"
            f"&id={app_id}&code={q}")


def load_public_codes(path=CURATED_PATH):
    """{app_id: {"code": ..., "source": ...}} from the curated file."""
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        raw = json.load(f)
    return {int(k): v for k, v in raw.items()}


def find_in_seller_site(app_id, seller_url):
    """Best-effort: fetch the developer's site and look for a redeem link
    for this app id. Returns (code, source_url) or (None, None)."""
    if not seller_url:
        return None, None
    try:
        req = urllib.request.Request(
            seller_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode(errors="ignore")
    except Exception as e:
        print(f"  [redeem] seller site fetch failed for {app_id}: {e}")
        return None, None
    for m in re.finditer(
            r'apps\.apple\.com/redeem\?[^"\s<>\']*id=%d[^"\s<>\']*'
            r'code=([A-Za-z0-9_-]+)' % app_id, html):
        return m.group(1), seller_url
    for m in re.finditer(
            r'apps\.apple\.com/redeem\?[^"\s<>\']*code=([A-Za-z0-9_-]+)'
            r'[^"\s<>\']*id=%d' % app_id, html):
        return m.group(1), seller_url
    return None, None


def find_public_code(app_id, app_name, seller_url, curated=None,
                     oodata=None):
    """Return (code, source) for a public custom offer code, or (None,
    None). Curated file first, then the oodata scrape, then the
    developer's own site. Never guesses."""
    if curated is None:
        curated = load_public_codes()
    if oodata is None:
        oodata = {}
    entry = curated.get(app_id)
    if entry and entry.get("code"):
        return entry["code"], entry.get("source", "curated")
    if app_id in oodata:
        return oodata[app_id]["code"], oodata[app_id].get("source", "oodata")
    code, src = find_in_seller_site(app_id, seller_url)
    if code:
        return code, src
    return None, None
