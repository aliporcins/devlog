#!/usr/bin/env python3
"""Set a GitHub Actions repo secret, encrypting with the repo public key
(libsodium sealed box) via the GitHub REST API + registered PAT connector.

Usage:
  python3 gh_set_secret.py <owner> <repo> <SECRET_NAME> <value>
  python3 gh_set_secret.py <owner> <repo> <SECRET_NAME> --from-file <path>
  python3 gh_set_secret.py <owner> <repo> <SECRET_NAME> --from-config <json> <key>

The value is read from the argument, a file, or a JSON config (key lookup)
so it never has to be typed in a shell. Never prints the value.
"""
import base64
import json
import sys

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from gh_push import api  # reuse the authed api() helper

from nacl import encoding, public


def main():
    owner, repo, name = sys.argv[1], sys.argv[2], sys.argv[3]
    if sys.argv[4] == "--from-file":
        with open(sys.argv[5]) as f:
            value = f.read().strip()
    elif sys.argv[4] == "--from-config":
        with open(sys.argv[5]) as f:
            value = json.load(f)[sys.argv[6]]
    else:
        value = sys.argv[4]

    status, key = api("GET",
                      f"/repos/{owner}/{repo}/actions/secrets/public-key")
    if status != 200:
        print(f"public key fetch failed: {status} {key}")
        return 1
    pub = public.PublicKey(key["key"].encode(),
                           encoding.Base64Encoder())
    sealed = public.SealedBox(pub).encrypt(value.encode())
    payload = {"encrypted_value": base64.b64encode(sealed).decode(),
               "key_id": key["key_id"]}
    status, out = api(
        "PUT", f"/repos/{owner}/{repo}/actions/secrets/{name}", payload)
    if status not in (201, 204):
        print(f"set secret failed: {status} {out}")
        return 1
    print(f"secret {name} set on {owner}/{repo} (status {status})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
