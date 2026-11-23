import os, subprocess, sys

# In GitHub Actions the token comes from the CLOUDFLARE_API_TOKEN secret.
# Locally, fall back to the registered Cloudflare connector credential.
token = os.environ.get("CLOUDFLARE_API_TOKEN")
if not token:
    sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
    from dynamic_credentials import dynamic_credential_entry
    token = dynamic_credential_entry("custom.cloudflare")["surrogate"]
account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID",
                            "56729b24f482638227bbb17f3c47382a")

env = dict(os.environ)
env["CLOUDFLARE_API_TOKEN"] = token
env["CLOUDFLARE_ACCOUNT_ID"] = account_id
# IMPORTANT: run from this directory so wrangler picks up wrangler.toml
# (D1 binding for the gate) and functions/ (login/setup/middleware).
# Running from anywhere else would deploy static files WITHOUT the gate.
r = subprocess.run(
    ["npx", "-y", "wrangler@3", "pages", "deploy",
     "site",
     "--project-name", "devlog", "--branch", "main", "--commit-dirty=true"],
    env=env, capture_output=True, text=True, timeout=300,
    cwd=os.path.dirname(os.path.abspath(__file__)))
tail = (r.stdout + r.stderr).strip().splitlines()
for line in tail[-8:]:
    print(line)
print("EXIT", r.returncode)
