#!/usr/bin/env python3
# One-time: trust your installer app on GitGuardian.
# Works with GitHub Enterprise Cloud and GitHub Enterprise Server 3.19 or later
# (set GITHUB_API_URL for GHES). Run with --check-only to test the GitHub side alone.
# pip install requests PyJWT cryptography
import os, sys
from urllib.parse import urlparse

import requests

from gh_api import (API, IS_GHES, MIN_GHES_FOR_ENTERPRISE_INSTALL, app_jwt, fmt_version,
                    get_all, ghes_version, headers)


def gitguardian_api_url():
    """Refuse anything that could send the API key or the signed token to the wrong place."""
    url = os.environ["GITGUARDIAN_API_URL"].strip().rstrip("/")
    parts = urlparse(url)
    if parts.scheme != "https":
        sys.exit(f"GITGUARDIAN_API_URL must start with https:// (got {url!r})")
    if not parts.netloc or parts.username or parts.query or parts.fragment:
        sys.exit(f"GITGUARDIAN_API_URL must be a plain base URL (got {url!r})")
    if parts.path not in ("", "/exposed"):
        sys.exit(
            "GITGUARDIAN_API_URL must be https://api.gitguardian.com, "
            "https://api.eu1.gitguardian.com, or https://<your-dashboard-host>/exposed "
            f"(got {url!r})"
        )
    return url


def check_github():
    """Run, against your own GitHub, the checks GitGuardian runs during registration.

    A failure here is reported before anything is sent to GitGuardian.
    """
    v = ghes_version()
    if isinstance(v, tuple) and v < MIN_GHES_FOR_ENTERPRISE_INSTALL:
        sys.exit(
            f"GitHub Enterprise Server {fmt_version(v)} cannot install apps on the enterprise "
            f"(requires {fmt_version(MIN_GHES_FOR_ENTERPRISE_INSTALL)} or later), so there is "
            "no installer app to register. Use gg_install_audit.py instead."
        )
    token = app_jwt()
    r = requests.get(f"{API}/app", headers=headers(token), timeout=30)
    if r.status_code != 200:
        sys.exit(
            f"{API} rejected the signed token ({r.status_code}): check GH_INSTALLER_CLIENT_ID, "
            "the private key, and GITHUB_API_URL."
        )
    app = r.json()
    installs = get_all(f"{API}/app/installations", token)
    if not any(i["target_type"] == "Enterprise" for i in installs):
        sys.exit(f"Installer app {app['slug']} is not installed on the enterprise (see step 2).")
    where = f"GHES {fmt_version(v)}" if IS_GHES else "GitHub Enterprise Cloud"
    print(f"GitHub check passed on {API} ({where}): app {app['slug']}, installed on the enterprise")


def main():
    check_github()
    if "--check-only" in sys.argv[1:]:
        return

    url = gitguardian_api_url()
    headers_gg = {"Authorization": f"Token {os.environ['GITGUARDIAN_API_KEY']}"}

    # Validate the URL and the API token before the signed token exists.
    health = requests.get(f"{url}/v1/health", headers=headers_gg, timeout=30)
    if health.status_code != 200:
        sys.exit(
            "GitGuardian did not accept the URL or the API token: "
            f"{health.status_code} {health.text[:200]}"
        )

    r = requests.post(
        f"{url}/v1/github/installer-app-rules",
        headers=headers_gg, json={"app_jwt": app_jwt()}, timeout=30,
    )
    if r.status_code == 409:
        print("Installer app already registered, nothing to do")
        return
    if r.status_code == 403 and IS_GHES:
        sys.exit(
            "GitGuardian rejected the registration (403). The GitHub-side checks passed, "
            "so if the API token has the sources:write scope and manager rights, contact "
            "GitGuardian support to confirm installer-app registration is enabled for "
            "GitHub Enterprise Server on your workspace."
        )
    r.raise_for_status()
    rule = r.json()
    print(f"Registered installer app {rule['installer_app_slug']} (bot id {rule['installer_bot_id']})")


main()
