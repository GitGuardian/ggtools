"""Shared GitHub helpers for GitHub Enterprise Cloud and GitHub Enterprise Server (GHES).

Which GitHub to talk to is set by GITHUB_API_URL:
  - GitHub Enterprise Cloud (github.com):  https://api.github.com   (default)
  - GitHub Enterprise Cloud with data residency (GHE.com):  https://api.<subdomain>.ghe.com
  - GitHub Enterprise Server:  https://<ghes-host>/api/v3

GitHub Actions sets GITHUB_API_URL (and GITHUB_SERVER_URL) automatically to the
instance the workflow runs on, so the scheduled workflow needs no extra setting.
"""
import os, sys, time
from urllib.parse import urlparse

import jwt, requests

# The enterprise organization-installations API first shipped in GHES 3.19.
MIN_GHES_FOR_ENTERPRISE_INSTALL = (3, 19)


def _api_url():
    url = (os.environ.get("GITHUB_API_URL") or "https://api.github.com").strip().rstrip("/")
    parts = urlparse(url)
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.query or parts.fragment:
        sys.exit(f"GITHUB_API_URL must be a plain https:// base URL (got {url!r})")
    return url


API = _api_url()
_HOST = (urlparse(API).hostname or "").lower()
IS_GHES = not (_HOST == "api.github.com" or _HOST.endswith(".ghe.com"))


def web_url():
    """Base URL of the GitHub web UI (for links shown to people)."""
    if os.environ.get("GITHUB_SERVER_URL"):
        return os.environ["GITHUB_SERVER_URL"].strip().rstrip("/")
    if _HOST == "api.github.com":
        return "https://github.com"
    if _HOST.startswith("api.") and _HOST.endswith(".ghe.com"):
        return "https://" + _HOST[len("api."):]
    return API[: -len("/api/v3")] if API.endswith("/api/v3") else API


def graphql_url():
    return API[: -len("/v3")] + "/graphql" if API.endswith("/api/v3") else API + "/graphql"


def headers(token=None):
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def app_jwt():
    """Short-lived token signed with the installer app's private key (10 minutes max)."""
    key = os.environ.get("GH_INSTALLER_PRIVATE_KEY") or open(
        os.environ["GH_INSTALLER_PRIVATE_KEY_PATH"]
    ).read()
    now = int(time.time())
    return jwt.encode(
        {"iat": now - 60, "exp": now + 540, "iss": os.environ["GH_INSTALLER_CLIENT_ID"]},
        key, algorithm="RS256",
    )


def get_all(url, token):
    """Follow GitHub's pagination: list endpoints return at most 100 items per page."""
    items = []
    url = f"{url}{'&' if '?' in url else '?'}per_page=100"
    while url:
        r = requests.get(url, headers=headers(token), timeout=30)
        r.raise_for_status()
        items.extend(r.json())
        url = r.links.get("next", {}).get("url")
    return items


def ghes_version(token=None):
    """(major, minor) of the GHES instance; None on Cloud; "unknown" if it can't be read.

    GHES reports its version in GET /meta (installed_version). Instances in
    private mode require authentication for /meta, so pass a token when one exists.
    """
    if not IS_GHES:
        return None
    try:
        r = requests.get(f"{API}/meta", headers=headers(token), timeout=30)
    except requests.RequestException as e:
        sys.exit(f"Cannot reach {API}: {e}")
    if r.status_code in (401, 403):
        return "unknown"
    r.raise_for_status()
    v = r.json().get("installed_version")
    if not v:
        return "unknown"
    try:
        return tuple(int(x) for x in v.split(".")[:2])
    except ValueError:
        return "unknown"


def fmt_version(v):
    return ".".join(map(str, v)) if isinstance(v, tuple) else str(v)
