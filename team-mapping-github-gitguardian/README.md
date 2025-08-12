# Team mapping: GitHub to GitGuardian

The included scripts provide an example of using the GitHub and GitGuardian
APIs to map GitHub members, teams and the repositories they own to GitGuardian users, teams and
their perimeters.

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
- `GITGUARDIAN_TOKEN` - A GitGuardian API Service Account Token with `teams:write`, `members:write` and `sources:read` permissions.

> [!TIP]
> If a Personal Access Token is used, the user who owns the PAT will be added
> to all teams when they're created. SATs are preferred for this reason.

Optional environment variables:

- `GITHUB_INSTANCE` - The URL of a self-hosted GitHub Enterprise Server instance. Just the scheme and hostname. By default it is set to https://github.example.com
- `GITGUARDIAN_INSTANCE` - The URL of a self-hosted GitGuardian instance. Just the scheme and hostname. By default it is set to https://gitguardian.example.com
- `LEVEL` - Level of logs to print. Refer to the [Python documentation](https://docs.python.org/3/library/logging.html#logging-levels) to see which level can be used. By default it is set to `INFO`.
- `NOTIFY_USER` - If an email should be sent when creating an invitation or adding/removing a user to/from a team. Default to `True`

You can also edit the config.yml at the root of this folder to add the following configuration:
- `email_blacklist` - A list of user emails present in your GitHub organization that you don't want to synchronize in GitGuardian

### Invoking

Upon invocation, the script will sync teams and their perimeters from GitHub to GitGuardian. It can be invoked like this:

```
python map_github_teams.py
```

### Data mapping

Each data is mapped between GitHub and GitGuardian following their email for members and invitations and their external id for teams and repositories. For teams, we store that information in their description field which should not be edited manually.

For nested team names, we use the following format on GitGuardian: "Parent team1 > Parent team2 > My team"

> [!WARNING]
> By default we will try to use IDP users because they nearly always provide the user
> email but if no IDP is set up we fall back on the org members. But in that case you
> may not have the access to the user's emails. If this is the case, the user will
> not be synchronized and a warning will be logged.
