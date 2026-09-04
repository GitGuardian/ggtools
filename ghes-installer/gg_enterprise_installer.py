#!/usr/bin/env python3
# Scheduled: install the GitGuardian app on every organization of the enterprise.
# pip install requests PyJWT cryptography
import os, sys, time

import jwt, requests

API = "https://api.github.com"

def app_jwt():
    key = os.environ.get("GH_INSTALLER_PRIVATE_KEY") or open(
        os.environ["GH_INSTALLER_PRIVATE_KEY_PATH"]
    ).read()
    now = int(time.time())
    return jwt.encode(
        {"iat": now - 60, "exp": now + 540, "iss": os.environ["GH_INSTALLER_CLIENT_ID"]},
        key, algorithm="RS256",
    )

def gh(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

def get_all(url, token):
    """Follow GitHub's pagination: list endpoints return at most 100 items per page."""
    items = []
    url = f"{url}{'&' if '?' in url else '?'}per_page=100"
    while url:
        r = requests.get(url, headers=gh(token), timeout=30)
        r.raise_for_status()
        items.extend(r.json())
        url = r.links.get("next", {}).get("url")
    return items

def enterprise_token():
    token = app_jwt()
    installs = get_all(f"{API}/app/installations", token)
    ent = next((i for i in installs if i["target_type"] == "Enterprise"), None)
    if ent is None:
        sys.exit("Installer app is not installed on the enterprise (see step 2).")
    r = requests.post(f"{API}/app/installations/{ent['id']}/access_tokens",
                      headers=gh(token), timeout=30)
    r.raise_for_status()
    return r.json()["token"]

def main():
    ent = os.environ["GH_ENTERPRISE_SLUG"]
    gg_app = os.environ["GG_APP_CLIENT_ID"]
    orgs = [a for a in sys.argv[1:] if a != "--all-orgs"]
    token = os.environ.get("GH_INSTALLATION_TOKEN") or enterprise_token()
    if not orgs:
        orgs = [o["login"] for o in get_all(
            f"{API}/enterprises/{ent}/apps/installable_organizations", token)]

    failed = 0
    for org in orgs:
        installed = get_all(
            f"{API}/enterprises/{ent}/apps/organizations/{org}/installations", token)
        if any(i.get("client_id") == gg_app for i in installed):
            print(org, "already installed, skipping")
            continue
        r = requests.post(
            f"{API}/enterprises/{ent}/apps/organizations/{org}/installations",
            headers=gh(token),
            json={"client_id": gg_app, "repository_selection": "all"},
            timeout=30,
        )
        if r.ok:
            print(org, "installed")
        else:
            failed += 1
            print(org, f"FAILED {r.status_code} {r.text[:100]}")
    sys.exit(1 if failed else 0)

main()
