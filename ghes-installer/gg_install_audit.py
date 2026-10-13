#!/usr/bin/env python3
# Audit: list the organizations missing the GitGuardian app, with an install link and
# the org owners to send it to. For GitHub Enterprise Server 3.18 and older, which have
# no API to install an app on an organization. Read-only: it installs nothing.
# Also works on GHES 3.19+ and on GitHub Enterprise Cloud.
# pip install requests PyJWT cryptography
import argparse, csv, os, sys

import requests

from gh_api import API, IS_GHES, fmt_version, get_all, ghes_version, graphql_url, headers

ENTERPRISE_ORGS_QUERY = """
query($slug: String!, $after: String) {
  enterprise(slug: $slug) {
    organizations(first: 100, after: $after) {
      nodes { login databaseId }
      pageInfo { hasNextPage endCursor }
    }
  }
}"""


def list_orgs(token, args):
    """Organizations to audit as (login, id): CLI arguments, else the enterprise, else the instance."""
    if args.orgs:
        out = []
        for login in args.orgs:
            r = requests.get(f"{API}/orgs/{login}", headers=headers(token), timeout=30)
            if r.status_code == 404:
                print(f"{login}: organization not found, skipping", file=sys.stderr)
                continue
            r.raise_for_status()
            out.append((r.json()["login"], r.json()["id"]))
        return out

    slug = os.environ.get("GH_ENTERPRISE_SLUG")
    if slug:
        out, after = [], None
        while True:
            r = requests.post(graphql_url(), headers=headers(token), timeout=30,
                              json={"query": ENTERPRISE_ORGS_QUERY,
                                    "variables": {"slug": slug, "after": after}})
            r.raise_for_status()
            body = r.json()
            ent = (body.get("data") or {}).get("enterprise")
            if not ent:
                sys.exit(f"Cannot list the organizations of enterprise {slug!r}: "
                         f"{body.get('errors') or 'not found'}. The token needs the "
                         "read:enterprise scope and an enterprise owner or member.")
            page = ent["organizations"]
            out += [(n["login"], n["databaseId"]) for n in page["nodes"]]
            if not page["pageInfo"]["hasNextPage"]:
                return out
            after = page["pageInfo"]["endCursor"]

    if IS_GHES:
        # On GHES every organization of the instance belongs to its one enterprise.
        return [(o["login"], o["id"]) for o in get_all(f"{API}/organizations", token)]
    sys.exit("On GitHub Enterprise Cloud, set GH_ENTERPRISE_SLUG or pass organization names.")


def audit_org(login, token, app_slug):
    """Return (status, owners). status: installed, missing, or unknown (no access)."""
    # This endpoint returns {"total_count", "installations"}, not a plain list.
    status, url = "missing", f"{API}/orgs/{login}/installations?per_page=100"
    while url:
        r = requests.get(url, headers=headers(token), timeout=30)
        if r.status_code in (403, 404):  # token is not an owner of this organization
            status = "unknown"
            break
        r.raise_for_status()
        if any(i.get("app_slug") == app_slug for i in r.json()["installations"]):
            status = "installed"
            break
        url = r.links.get("next", {}).get("url")
    try:
        owners = [m["login"] for m in get_all(f"{API}/orgs/{login}/members?role=admin", token)]
    except requests.HTTPError:
        owners = []
    return status, owners


def main():
    p = argparse.ArgumentParser(
        description="List organizations missing the GitGuardian app, with install links.")
    p.add_argument("orgs", nargs="*", help="organizations to audit (default: all)")
    p.add_argument("--csv", default="gg_install_audit.csv", help="CSV report path")
    p.add_argument("--md", default="gg_install_audit.md", help="Markdown report path")
    p.add_argument("--include-installed", action="store_true",
                   help="also list organizations that already have the app")
    args = p.parse_args()

    token = os.environ["GH_TOKEN"]
    app_slug = os.environ["GG_APP_SLUG"]

    r = requests.get(f"{API}/apps/{app_slug}", headers=headers(token), timeout=30)
    if r.status_code == 404:
        sys.exit(f"GitHub App {app_slug!r} not found on {API}. On GHES, use the slug of the "
                 "GitGuardian app created on your instance (from its URL /github-apps/<slug>).")
    r.raise_for_status()
    app = r.json()
    version = ghes_version(token)
    print(f"GitHub: {API}" + (f" (GHES {fmt_version(version)})" if IS_GHES else "")
          + f", app: {app['name']} ({app_slug})")
    if isinstance(version, tuple) and version >= (3, 19):
        print("Note: this GHES version can install apps by API; gg_enterprise_installer.py "
              "can do the installs for you.")

    rows = []
    for login, org_id in list_orgs(token, args):
        status, owners = audit_org(login, token, app_slug)
        print(f"{login}: {status}")
        if status == "installed" and not args.include_installed:
            continue
        rows.append({
            "organization": login,
            "status": status,
            "install_url": "" if status == "installed" else
            f"{app['html_url']}/installations/new/permissions?target_id={org_id}",
            "org_owners": " ".join(owners),
        })

    with open(args.csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["organization", "status", "install_url", "org_owners"])
        w.writeheader()
        w.writerows(rows)
    with open(args.md, "w") as f:
        f.write(f"# GitGuardian app install audit\n\nApp: {app['name']} on {API}\n\n")
        f.write("| Organization | Status | Install link | Org owners |\n|---|---|---|---|\n")
        for row in rows:
            link = f"[Install]({row['install_url']})" if row["install_url"] else ""
            owners = ", ".join(f"@{o}" for o in row["org_owners"].split()) or "(not visible)"
            f.write(f"| {row['organization']} | {row['status']} | {link} | {owners} |\n")

    counts = {s: sum(r["status"] == s for r in rows) for s in ("missing", "unknown")}
    print(f"\n{counts['missing']} missing, {counts['unknown']} unknown (token cannot read the "
          f"org's installations). Reports: {args.csv}, {args.md}")


main()
