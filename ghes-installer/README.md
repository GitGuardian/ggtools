# Installing GitGuardian across your GitHub Enterprise

This guide explains how to install the GitGuardian GitHub App on **all organizations of your GitHub Enterprise automatically**, using GitHub's enterprise installation API and two small scripts: a one-time registration, and an install loop that runs on a schedule. Once set up, no one needs to click through the GitGuardian dashboard for each organization, and organizations you create in the future are covered by the next scheduled run.

## How it works

GitHub lets an enterprise create its own "installer" GitHub App. Once that app is installed on your enterprise, it can install any other GitHub App (including GitGuardian's) into your organizations with a single API call.

On the GitGuardian side, you register this installer app **once** on your workspace. From then on, every installation your installer app performs is recognized and linked to your workspace automatically, the moment GitHub delivers it. Repositories start syncing right away.

The registration is authenticated with a short-lived token signed by your installer app's private key. GitHub itself verifies the signature, which proves the registration comes from the app's real owner. The key never leaves your infrastructure. GitGuardian uses the signed token during the registration request only and does not store it: see *What GitGuardian does with the signed token* below.

## Prerequisites

| You need | Details |
| --- | --- |
| GitHub Enterprise Cloud | An enterprise account on [github.com](http://github.com) with your organizations under it |
| GitHub enterprise owner | Required once, to create and install the installer app |
| GitGuardian workspace manager | Required once, to create the API token used for registration |
| Python 3.10+ | To run the scripts (`pip install requests PyJWT cryptography`). For the scheduled install loop, a GitHub Actions workflow is recommended (step 4) |

## Setup

The easiest method of installation is to use Python virtual environment (venv):

```shell
python3 -mvenv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Step 1. Create your installer app (once)

As an enterprise owner, in your browser:

1. Go to `https://github.com/enterprises/<your-slug>/settings/apps` and click **New GitHub App**.
2. Give it any name (for example `gitguardian-installer`) and any homepage URL.
3. Under **Webhook**, uncheck **Active**. The installer app does not need webhooks.
4. Under **Permissions**, open the **Enterprise permissions** section and set **Enterprise organization installations** to **Read and write**. Leave every other permission on *No access*.
5. Click **Create GitHub App**.
6. On the app's page, note the **Client ID**, then click **Generate a private key**. A `.pem` file downloads.

> ⚠️ **This key is more powerful than a GitGuardian credential.** Because of the permission from item 4, whoever holds it can install *any* GitHub App, with access to all repositories, on *every* organization of your enterprise, and uninstall apps as well. GitHub offers no narrower permission for this. Treat the key as an enterprise-owner-level secret: keep it in GitHub Actions secrets or a secrets manager, never on a shared host or in a repository. See *About the private key* below.
>

## Step 2. Install the app on your enterprise (once)

Still on the app's settings page, open **Install App** in the left sidebar and install it on the **enterprise itself**, not on an individual organization. The enterprise appears as an install target because of the enterprise permission from step 1.

## Step 3. Register the installer app on GitGuardian (once)

This step tells GitGuardian to trust your installer app. It runs once, from any machine that can read the `.pem` file, and is the only step that talks to GitGuardian.

1. In your GitGuardian workspace, as a manager, create an API token (personal or service account) with the **`sources:write`** scope: Settings → API → Personal access tokens / Service accounts. Give it a short expiration: it is needed for this step only.
2. Set the variables below and run `python3 gg_register_installer.py`.
3. Revoke the API token. The registration is permanent, so the token has no further use.

| Variable | Value |
| --- | --- |
| `GH_INSTALLER_CLIENT_ID` | Your installer app's Client ID (step 1) |
| `GH_INSTALLER_PRIVATE_KEY_PATH` | Path to the downloaded `.pem` file (or put the key content itself in `GH_INSTALLER_PRIVATE_KEY`) |
| `GITGUARDIAN_API_URL` | The GitGuardian API base URL, the same value you would give ggshield: `https://api.gitguardian.com` (SaaS, US), `https://api.eu1.gitguardian.com` (SaaS, EU), or `https://<your-dashboard-host>/exposed` (self-hosted). It must use `https://` |
| `GITGUARDIAN_API_KEY` | The API token from item 1 |

The script checks the URL and the API token against the API health endpoint before it mints or sends the signed token, so a typo cannot send anything to the wrong place. It exits with `already registered` when run again.

### The registration script

```python
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
```

## Step 4. Install GitGuardian on your organizations (scheduled)

The install loop lists the organizations of your enterprise and installs the GitGuardian app where it is missing. It needs an installation access token of your installer app and nothing from GitGuardian. Run it on a schedule so new organizations get covered.

### Recommended: a GitHub Actions workflow

Run the loop as a scheduled workflow in a private repository of one of your organizations. The private key then lives in GitHub's encrypted Actions secrets: no long-lived key on a self-managed cron host, no extra infrastructure to secure, and every run is logged in the workflow history.

1. Commit `gg_enterprise_installer.py` (below) to the repository.
2. In the repository settings, add the secret `GH_INSTALLER_PRIVATE_KEY` with the content of the `.pem` file, and the variables `GH_INSTALLER_CLIENT_ID`, `GH_ENTERPRISE_SLUG`, and `GG_APP_CLIENT_ID` (the GitGuardian app's client ID, provided by GitGuardian).
3. Add this workflow:

```yaml
name: Install GitGuardian across the enterprise
on:
  schedule:
    - cron: "0 7 * * *"
  workflow_dispatch:

jobs:
  install:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install requests PyJWT cryptography
      - run: python3 gg_enterprise_installer.py --all-orgs
        env:
          GH_INSTALLER_CLIENT_ID: ${{ vars.GH_INSTALLER_CLIENT_ID }}
          GH_INSTALLER_PRIVATE_KEY: ${{ secrets.GH_INSTALLER_PRIVATE_KEY }}
          GH_ENTERPRISE_SLUG: ${{ vars.GH_ENTERPRISE_SLUG }}
          GG_APP_CLIENT_ID: ${{ vars.GG_APP_CLIENT_ID }}
```

### Alternative: your own scheduler

If you cannot use GitHub Actions, run the same script from your scheduler with these variables:

| Variable | Value |
| --- | --- |
| `GH_INSTALLER_CLIENT_ID` | Your installer app's Client ID (step 1) |
| `GH_INSTALLER_PRIVATE_KEY_PATH` | Path to the `.pem` file (or the key content in `GH_INSTALLER_PRIVATE_KEY`). Prefer fetching it from a secrets manager at runtime |
| `GH_ENTERPRISE_SLUG` | Your enterprise slug (as in `github.com/enterprises/<slug>`) |
| `GG_APP_CLIENT_ID` | The GitGuardian app's client ID (provided by GitGuardian) |
| `GH_INSTALLATION_TOKEN` (optional) | A 1-hour installation token of your installer app minted by a secured component. When set, the loop does not need the key at all and the two `GH_INSTALLER_*` variables can be omitted |

```bash
# every organization of the enterprise
python3 gg_enterprise_installer.py --all-orgs
# specific organizations
python3 gg_enterprise_installer.py org-one org-two
# for example, daily
0 7 * * * python3 /path/to/gg_enterprise_installer.py --all-orgs
```

The script is idempotent: organizations that already have the app are skipped. It exits with a non-zero status when at least one installation failed, so a scheduled run shows up as failed.

### The install script

```python
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
```

Each installation appears in your GitGuardian workspace within seconds, already linked, with all repositories of the organization syncing (`repository_selection: all`).

## Verifying

- In GitGuardian: **Settings → Integrations → GitHub** lists every installed organization, and the **Sources** page fills with repositories as syncing completes.
- In the **Audit log**: one entry per organization ("automatically added the GitHub installation of ‹org› to the workspace"), plus one entry for the installer app registration.
- On GitHub: each organization's **Settings → GitHub Apps** shows the GitGuardian app installed.

## About the private key

A question that came up during the discussion of the solution: can this run with just a GitHub token, without the `.pem` file? No, and the requirement comes from GitHub, not GitGuardian: the enterprise installation API only accepts GitHub App authentication, and personal access tokens are explicitly not supported there. App authentication always starts from the app's private key.

What this means in practice:

- **What the key can do.** With the *Enterprise organization installations* permission, the key can install any GitHub App, with access to all repositories, on every organization of your enterprise, and uninstall apps too. GitHub offers no narrower permission for this. Protect the key like an enterprise-owner credential.
- **Prefer GitHub Actions secrets** for the scheduled loop (step 4). If the loop must run elsewhere, keep the key in a secrets manager rather than on disk and fetch it at runtime; only `app_jwt()` needs to change.
- **The key never leaves your infrastructure.** The scripts only transmit short-lived derived tokens: the signed token, valid for 10 minutes, goes to GitHub and, once during registration, to GitGuardian; the installation token, valid for 1 hour, goes to GitHub only. GitGuardian never receives or stores the key; it receives the signed token only, as described in the next section.
- **The install loop can run without the key at all**: a secured component can mint the 1-hour installation token and hand only that token to the loop through `GH_INSTALLATION_TOKEN`.
- If the key is ever compromised, revoke it on the app's settings page and generate a new one. Nothing needs to change on the GitGuardian side: the registration is tied to the app, not to the key.

## What GitGuardian does with the signed token

The signed token is sent once, in the body of the registration call. GitGuardian uses it during that request only, for four GitHub API calls, then discards it:

1. `GET /app`, authenticated with your signed token. GitHub verifies the signature and returns the app's identity: app ID, slug, and owner.
2. `GET /app/installations`, authenticated with your signed token. This confirms the app is installed on your enterprise (step 2). Registration is refused otherwise.
3. `POST /app/installations/<id>/access_tokens`, authenticated with your signed token. This exchanges it for an installation access token of your installer app, valid for one hour. That token carries the same permission as your installer app (*Enterprise organization installations: read and write*).
4. `GET /users/<slug>[bot]`, authenticated with that installation token. This resolves the numeric ID of the app's bot user, which is what GitHub reports as the sender of every installation the app performs. GitHub does not allow this lookup with a signed token, hence step 3.

GitGuardian keeps only public identifiers from these responses: the app ID, the slug, the owner login, and the bot user ID. Neither the signed token nor the installation token is stored or reused after the request; the installation token is used for the single read in step 4 and expires on its own after one hour. Because the signed token is a bearer credential while it is valid, mint it right before the call and keep its lifetime short, as the script does (10 minutes, the maximum GitHub accepts).

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Registration exits with `GITGUARDIAN_API_URL must ...` | The URL is not a plain `https://` base URL. Use `https://api.gitguardian.com`, `https://api.eu1.gitguardian.com`, or `https://<your-dashboard-host>/exposed` |
| Registration exits with `GitGuardian did not accept the URL or the API token` | Wrong region or instance URL, or the API token is expired or mistyped. Nothing was sent to GitGuardian besides the token check |
| Registration returns **403** | The signed token was rejected: expired (the script mints it right before the call), wrong private key file, or wrong Client ID. Also returned when the API token lacks the `sources:write` scope or manager rights |
| Registration prints `already registered` | The installer app is already trusted by your workspace. Nothing to do |
| `Installer app is not installed on the enterprise` | Step 2 was skipped, or the app was installed on an organization instead of the enterprise |
| Install call returns **404** | The installer app lacks the *Enterprise organization installations: write* permission, or `GG_APP_CLIENT_ID` is empty or wrong |
| Organization reported as `already installed, skipping` | Nothing to do: the app is already on that organization |
| Installation appears on GitHub but not in GitGuardian | Step 3 was never completed for this installer app. Run the registration script, then reinstall the organization |
