#!/usr/bin/env python3
"""3-day expiry cleanup for the free-apps pipeline.

- Re-checks the price of every app posted in the last 7 days (iTunes
  Lookup). Any app back to paid is removed from its blog post (section
  deleted, headings renumbered, counts updated) and its Telegram channel
  messages are deleted (message IDs from automation/data/<date>/posted.json).
- Deletes blog posts + asset dirs older than 7 days (Cloudflare Pages
  file-count limit), then rebuilds and redeploys (deploy needs
  CLOUDFLARE_API_TOKEN; without it the rebuild still runs and deploy is
  skipped with a clear message).

Usage:
  python3 cleanup.py [--date YYYY-MM-DD] [--dry-run]
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scrape as sc
from pipeline import lookup, ROOT, DATA_DIR, POSTS_DIR, ASSETS_DIR

CHANNEL_ID = os.environ.get("TG_CHANNEL_ID", "-1004423043910")


def get_token():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        return token
    with open(os.path.expanduser(
            "~/workspace/telegram-freeapps-bot/config.json")) as f:
        return json.load(f)["bot_token"]


def tg_delete(token, message_id):
    import urllib.error
    url = f"https://api.telegram.org/bot{token}/deleteMessage"
    data = json.dumps({"chat_id": CHANNEL_ID,
                       "message_id": message_id}).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r).get("ok", False)
    except urllib.error.HTTPError as e:
        print(f"  delete {message_id} failed: HTTP {e.code}")
        return False
    except Exception as e:
        print(f"  delete {message_id} failed: {e}")
        return False


def remove_app_from_post(md, app_name, section):
    """Remove one app's '### N. Name' block from the given section.

    section: 'paid' or 'iap'. Returns (new_md, removed_bool).
    """
    if section == "paid":
        sec_re = re.compile(r"(## 付费应用限时免费.*?)(\n## 终身内购|\Z)", re.S)
        count_re = re.compile(r"（(\d+) 款）")
    else:
        sec_re = re.compile(r"(## 终身内购.*)", re.S)
        count_re = re.compile(r"（(\d+) 个）")
    m = sec_re.search(md)
    if not m:
        return md, False
    sec = m.group(1)
    # Split into per-app blocks; keep the header part before the first ###
    parts = re.split(r"(\n### \d+\. )", sec)
    head, blocks = parts[0], parts[1:]
    kept, removed = [], False
    for i in range(0, len(blocks), 2):
        marker, body = blocks[i], blocks[i + 1]
        name = body.split("\n", 1)[0].strip()
        if name == app_name:
            removed = True
            continue
        kept.append((marker, body))
    if not removed:
        return md, False
    # Renumber
    new_sec = head
    for j, (marker, body) in enumerate(kept, 1):
        new_sec += re.sub(r"\n### \d+\. ", f"\n### {j}. ", marker, count=1) + body
    # Update the count in the section header
    cm = count_re.search(new_sec)
    if cm:
        n = int(cm.group(1)) - 1
        new_sec = count_re.sub(f"（{n} {'款' if section == 'paid' else '个'}）",
                               new_sec, count=1)
    md = md[:m.start(1)] + new_sec + md[m.end(1):]
    return md, True


def update_counts(md, paid_n=None, iap_n=None):
    """Update the N counts in title / excerpt / intro paragraph."""
    if paid_n is not None:
        md = re.sub(r"(\d+) 款付费应用免费领", f"{paid_n} 款付费应用免费领", md)
        md = re.sub(r"今天 (\d+) 款付费 App", f"今天 {paid_n} 款付费 App", md)
    if iap_n is not None:
        md = re.sub(r"(\d+) 个终身内购 0 元兑", f"{iap_n} 个终身内购 0 元兑", md)
        md = re.sub(r"另有 (\d+) 个终身内购", f"另有 {iap_n} 个终身内购", md)
    return md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    date = args.date or datetime.date.today().isoformat()
    today = datetime.date.fromisoformat(date)
    print(f"== cleanup {date} (dry-run={args.dry_run}) ==")

    # Load posted record: {app_id: date}
    posted_path = os.path.join(DATA_DIR, "posted.json")
    posted = {}
    if os.path.isfile(posted_path):
        with open(posted_path) as f:
            posted = {int(k): v for k, v in json.load(f).items()}

    # 1. Re-check prices of apps posted in the last 7 days
    cutoff = (today - datetime.timedelta(days=7)).isoformat()
    expired = []  # (app_id, posted_date)
    for app_id, posted_date in sorted(posted.items()):
        if posted_date < cutoff:
            continue
        rec = lookup(app_id)
        if rec is None:
            continue  # gone from store; leave the post alone
        if rec.get("price", 0) != 0:
            expired.append((app_id, posted_date))
            print(f"  expired: {app_id} {rec.get('trackName')} "
                  f"(posted {posted_date}, now ${rec.get('price')})")
        time.sleep(0.3)
    print(f"expired apps: {len(expired)}")

    token = None if args.dry_run else get_token()
    for app_id, posted_date in expired:
        # Find the app's name + section from its post
        post_path = os.path.join(POSTS_DIR, f"{posted_date}-free-apps.md")
        if not os.path.isfile(post_path):
            continue
        with open(post_path, encoding="utf-8") as f:
            md = f.read()
        # name from iTunes (fallback: search the post for the id link)
        rec = lookup(app_id)
        name = rec.get("trackName", "") if rec else ""
        section = None
        for sec in ("paid", "iap"):
            if f"id{app_id}" in md:
                # figure out which section the link is in
                paid_sec = re.search(r"## 付费应用限时免费.*?(?=\n## 终身内购|\Z)",
                                     md, re.S)
                if paid_sec and f"id{app_id}" in paid_sec.group(0):
                    section = "paid"
                else:
                    section = "iap"
                break
        if not section:
            continue
        # The post's heading name may differ slightly from trackName; find it
        sec_re = (re.compile(r"## 付费应用限时免费.*?(?=\n## 终身内购|\Z)", re.S)
                  if section == "paid" else
                  re.compile(r"## 终身内购.*", re.S))
        sec_m = sec_re.search(md)
        heading = None
        if sec_m:
            for hm in re.finditer(r"\n### \d+\. ([^\n]+)", sec_m.group(0)):
                if f"id{app_id}" in sec_m.group(0)[
                        hm.start():sec_m.group(0).find("\n### ", hm.start() + 1)
                        if sec_m.group(0).find("\n### ", hm.start() + 1) > 0
                        else len(sec_m.group(0))]:
                    heading = hm.group(1).strip()
                    break
        if not heading:
            heading = name
        new_md, removed = remove_app_from_post(md, heading, section)
        if removed:
            # Also drop it from the featured list if present
            new_md = re.sub(
                rf"\n\d+\. \*\*{re.escape(heading)}\*\* — [^\n]*", "",
                new_md, count=1)
            # Update counts
            paid_n = len(re.findall(r"\n### \d+\. ",
                                    re.search(r"## 付费应用限时免费.*?(?=\n## 终身内购|\Z)",
                                              new_md, re.S).group(0))) \
                if re.search(r"## 付费应用限时免费", new_md) else 0
            iap_m = re.search(r"## 终身内购.*", new_md, re.S)
            iap_n = len(re.findall(r"\n### \d+\. ", iap_m.group(0))) \
                if iap_m else 0
            new_md = update_counts(new_md, paid_n=paid_n, iap_n=iap_n)
            if not args.dry_run:
                with open(post_path, "w", encoding="utf-8") as f:
                    f.write(new_md)
            print(f"  removed {heading} from {posted_date} post")
            # Delete its channel messages
            posted_json = os.path.join(DATA_DIR, posted_date, "posted.json")
            if os.path.isfile(posted_json) and not args.dry_run:
                with open(posted_json) as f:
                    pj = json.load(f)
                for key, mids in list(pj.items()):
                    if key in (f"app:https://apps.apple.com/us/app/id{app_id}",
                               f"iap:https://apps.apple.com/us/app/id{app_id}"):
                        for mid in mids:
                            tg_delete(token, mid)
                        del pj[key]
                with open(posted_json, "w") as f:
                    json.dump(pj, f, indent=1)
            del posted[app_id]
    if not args.dry_run:
        with open(posted_path, "w") as f:
            json.dump({str(k): v for k, v in posted.items()}, f, indent=1)

    # 2. Delete posts + assets older than 7 days
    removed_posts = 0
    for fn in os.listdir(POSTS_DIR):
        m = re.match(r"(\d{4}-\d{2}-\d{2})-free-apps\.md$", fn)
        if not m:
            continue
        if m.group(1) < cutoff:
            print(f"  deleting old post {fn}")
            if not args.dry_run:
                os.remove(os.path.join(POSTS_DIR, fn))
                adir = os.path.join(
                    ASSETS_DIR, f"free-apps-{m.group(1).replace('-', '')}")
                if os.path.isdir(adir):
                    shutil.rmtree(adir)
                ddir = os.path.join(DATA_DIR, m.group(1))
                if os.path.isdir(ddir):
                    shutil.rmtree(ddir)
            removed_posts += 1
    print(f"old posts removed: {removed_posts}")

    # 3. Rebuild (+ deploy if token present)
    if expired or removed_posts:
        print("-- rebuild --")
        if not args.dry_run:
            r = os.system(f"cd {ROOT} && python3 build.py")
            if r == 0 and os.environ.get("CLOUDFLARE_API_TOKEN"):
                os.system(f"cd {ROOT} && python3 deploy.py")
            elif r == 0:
                print("CLOUDFLARE_API_TOKEN not set; deploy skipped")
    print("== done ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
