# Team mapping: GitHub to GitGuardian

The included scripts provide an example of using the GitHub and GitGuardian
APIs to map GitHub Teams and the repositories they own to GitGuardian Teams and
their perimeters.

This code _does not_ map team membership from GitHub to GitGuardian--only
repositories are mapped. The GitHub APIs don't provide email addresses for most
users so there's no simple way to map them to GitGuardain members.

> [!CAUTION]
> This is example code that can be used as a starting point for your own
> solution. While we're happy to answer questions about it _it is not a
> supported part of the product_.

### Installation

The easiest method of installation is to use Python virtual environment (venv):

```
unzip team-mapping-github-gitguardian.zip
cd team-mapping-github-gitguardian
python3 -mvenv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Three environment variables must be set to configure the connection:

- `GITHUB_ORG` - The name of a GitHub Org that teams will be copied from.
- `GITHUB_TOKEN` - A GitHub token (classic) with `read:org` and `repo` permissions.
- `GITGUARDIAN_TOKEN` - A GitGuardian API Service Account Token with `teams:read`, `teams:write` and `sources:read` permissions.

> [!TIP]
> If a Personal Access Token is used, the user who owns the PAT will be added
> to all teams when they're created. SATs are preferred for this reason.

Optional environment variables:

- `GITHUB_INSTANCE` - The URL of a self-hosted GitHub Enterprise Server instance. Just the scheme and hostname: https://github.example.com
- `GITGUARDIAN_INSTANCE` - The URL of a self-hosted GitGuardian instance. Just the scheme and hostname: https://gitguardian.example.com

### Invoking

Upon invocation, the script will sync teams and their perimeters from GitHub to GitGuardian. It can be invoked like this:

```
python map_github_teams.py
```
