#!/usr/bin/env python3
# Scheduled: install the GitGuardian app on every organization of the enterprise.
# Works on GitHub Enterprise Cloud and on GitHub Enterprise Server 3.19 or later
# (set GITHUB_API_URL for GHES). For GHES 3.18 and older, use gg_install_audit.py.
# pip install requests PyJWT cryptography
import os, sys

import requests

from gh_api import (API, IS_GHES, MIN_GHES_FOR_ENTERPRISE_INSTALL, app_jwt, fmt_version,
                    get_all, ghes_version, headers)


def enterprise_token():
    token = app_jwt()
    installs = get_all(f"{API}/app/installations", token)
    ent = next((i for i in installs if i["target_type"] == "Enterprise"), None)
    if ent is None:
        sys.exit("Installer app is not installed on the enterprise (see step 2)."
                 + (" On GHES this also happens on versions older than 3.19, which cannot"
                    " install apps on the enterprise." if IS_GHES else ""))
    r = requests.post(f"{API}/app/installations/{ent['id']}/access_tokens",
                      headers=headers(token), timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def check_ghes_version(token=None):
    """Stop early, with a clear message, on GHES versions without the enterprise install API."""
    v = ghes_version(token)
    if v is None or v == "unknown":
        return v
    if v < MIN_GHES_FOR_ENTERPRISE_INSTALL:
        sys.exit(
            f"GitHub Enterprise Server {fmt_version(v)} does not have the enterprise "
            f"organization-installations API (it requires GHES "
            f"{fmt_version(MIN_GHES_FOR_ENTERPRISE_INSTALL)} or later). "
            "Upgrade GHES, or run gg_install_audit.py to list the organizations "
            "missing the GitGuardian app with an install link for each."
        )
    return v


def main():
    ent = os.environ["GH_ENTERPRISE_SLUG"]
    gg_app = os.environ["GG_APP_CLIENT_ID"]
    orgs = [a for a in sys.argv[1:] if a != "--all-orgs"]

    version = check_ghes_version()  # unauthenticated first; private-mode GHES needs a token
    token = os.environ.get("GH_INSTALLATION_TOKEN") or enterprise_token()
    if version == "unknown":
        version = check_ghes_version(token)
    print(f"GitHub: {API}" + (f" (GHES {fmt_version(version)})" if IS_GHES else ""))

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
            headers=headers(token),
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
