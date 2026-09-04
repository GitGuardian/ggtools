#!/usr/bin/env python3
# One-time: trust your installer app on GitGuardian.
# pip install requests PyJWT cryptography
import os, sys, time
from urllib.parse import urlparse

import jwt, requests

def app_jwt():
    key = os.environ.get("GH_INSTALLER_PRIVATE_KEY") or open(
        os.environ["GH_INSTALLER_PRIVATE_KEY_PATH"]
    ).read()
    now = int(time.time())
    return jwt.encode(
        {"iat": now - 60, "exp": now + 540, "iss": os.environ["GH_INSTALLER_CLIENT_ID"]},
        key, algorithm="RS256",
    )

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

def main():
    url = gitguardian_api_url()
    headers = {"Authorization": f"Token {os.environ['GITGUARDIAN_API_KEY']}"}

    # Validate the URL and the API token before the signed token exists.
    health = requests.get(f"{url}/v1/health", headers=headers, timeout=30)
    if health.status_code != 200:
        sys.exit(
            "GitGuardian did not accept the URL or the API token: "
            f"{health.status_code} {health.text[:200]}"
        )

    r = requests.post(
        f"{url}/v1/github/installer-app-rules",
        headers=headers, json={"app_jwt": app_jwt()}, timeout=30,
    )
    if r.status_code == 409:
        print("Installer app already registered, nothing to do")
        return
    r.raise_for_status()
    rule = r.json()
    print(f"Registered installer app {rule['installer_app_slug']} (bot id {rule['installer_bot_id']})")

main()