#!/usr/bin/env python3
"""Create the GitHub repo (if needed) and push a local directory as the
initial commit, using the Git Data API via the registered GitHub PAT
connector (same credential path as gh.py). Handles binary files (base64).

Usage:
  python3 gh_push.py <owner> <repo> <local_dir> [branch] [--public|--private]

- If the repo does not exist, it is created (public by default).
- If the repo is empty, it is bootstrapped with one tiny commit first
  (the Git Data API refuses blobs in a completely empty repo), then the
  full tree is pushed on top.
- If the repo already has commits, the new tree is pushed as a new commit
  on top of the current HEAD (the tree replaces the previous one wholesale,
  so only run this on a repo that is a mirror of the local directory).
Never prints the token.
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request

BASE = "https://api.github.com"


def api(method, path, payload=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    add_surrogate_to_request(req, "custom.github-pat",
                             allowed_hosts=["api.github.com"])
    body = json.dumps(payload).encode() if payload is not None else None
    if body:
        req.add_header("Content-Type", "application/json")
    opener = urllib.request.build_opener()
    try:
        with opener.open(req, data=body, timeout=120) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "{}")
        except Exception:
            return e.code, {"raw": raw[:1000]}


def is_text(data):
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def main():
    owner, repo, local_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    branch = sys.argv[4] if len(sys.argv) > 4 else "main"
    private = "--private" in sys.argv

    # 1. Repo exists?
    status, repo_info = api("GET", f"/repos/{owner}/{repo}")
    if status == 404:
        print(f"creating repo {owner}/{repo} ...")
        status, repo_info = api("POST", "/user/repos", {
            "name": repo, "private": private, "auto_init": False,
            "description": "Personal devlog blog + daily iOS free-apps automation",
        })
        if status not in (201, 202):
            print(f"create repo failed: {status} {repo_info}")
            return 1
        print(f"repo created: {repo_info.get('html_url')}")
    elif status != 200:
        print(f"repo check failed: {status} {repo_info}")
        return 1
    else:
        print(f"repo exists: {repo_info.get('html_url')}")

    # 2. Is it empty? If so, bootstrap with one file via the Contents API
    # (the Git Data API refuses blobs in a completely empty repo: 409).
    status, ref = api("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}")
    parent_sha = None
    if status in (404, 409, 422):
        # empty repo (GitHub answers 409 "Git Repository is empty" here)
        print("empty repo; bootstrapping with a first commit ...")
        status, out = api(
            "PUT", f"/repos/{owner}/{repo}/contents/.gitkeep", {
                "message": "Initialize repository",
                "content": base64.b64encode(b"initial\n").decode(),
            })
        if status not in (201, 202):
            print(f"bootstrap failed: {status} {out}")
            return 1
        parent_sha = out["commit"]["sha"]
        print(f"bootstrap commit {parent_sha[:12]}")
    elif status == 200:
        parent_sha = ref["object"]["sha"]
        print(f"branch {branch} at {parent_sha[:12]}; new commit on top")
    else:
        print(f"ref check failed: {status} {ref}")
        return 1

    # 3. Collect files (skip .git, site/, __pycache__)
    files = []
    for root, dirs, names in os.walk(local_dir):
        dirs[:] = [d for d in dirs
                   if d not in (".git", "site", "__pycache__", ".wrangler")]
        for n in names:
            if n.endswith(".pyc"):
                continue
            full = os.path.join(root, n)
            rel = os.path.relpath(full, local_dir).replace(os.sep, "/")
            files.append((rel, full))
    files.sort()
    print(f"{len(files)} files, "
          f"{sum(os.path.getsize(f) for _, f in files) / 1e6:.1f} MB")

    # 4. Create blobs
    blobs = []
    for rel, full in files:
        with open(full, "rb") as fh:
            data = fh.read()
        if is_text(data):
            payload = {"content": data.decode("utf-8"), "encoding": "utf-8"}
        else:
            payload = {"content": base64.b64encode(data).decode(),
                       "encoding": "base64"}
        status, out = api("POST", f"/repos/{owner}/{repo}/git/blobs", payload)
        if status != 201:
            print(f"blob failed for {rel}: {status} {out}")
            return 1
        blobs.append({"path": rel, "mode": "100644", "type": "blob",
                      "sha": out["sha"]})
    print(f"blobs created: {len(blobs)}")

    # 5. Tree + commit + ref
    status, tree = api("POST", f"/repos/{owner}/{repo}/git/trees",
                       {"tree": blobs})
    if status != 201:
        print(f"tree failed: {status} {tree}")
        return 1
    status, commit = api("POST", f"/repos/{owner}/{repo}/git/commits", {
        "message": "Initial commit: devlog blog + free-apps automation",
        "tree": tree["sha"], "parents": [parent_sha] if parent_sha else [],
    })
    if status != 201:
        print(f"commit failed: {status} {commit}")
        return 1
    status, out = api("PATCH",
                      f"/repos/{owner}/{repo}/git/refs/heads/{branch}", {
                          "sha": commit["sha"], "force": False,
                      })
    if status != 200:
        print(f"ref update failed: {status} {out}")
        return 1
    print(f"pushed: {repo_info.get('html_url')} "
          f"branch {branch} commit {commit['sha'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
