# Team mapping: Gitlab to GitGuardian

The included scripts provide an example of using the Gitlab and GitGuardian
APIs to map Gitlab groups and the repositories they own to GitGuardian Teams and
their perimeters.

> [!CAUTION]
> This is example code that can be used as a starting point for your own
> solution. While we're happy to answer questions about it _it is not a
> supported part of the product_.

### Installation

The easiest method of installation is to use Python virtual environment (venv):

```
unzip team-mapping-gitlab-gitguardian.zip
cd team-mapping-gitlab-gitguardian
python3 -mvenv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Three environment variables must be set to configure the connection:

- `GITLAB_URL` - The base URL for your Gitlab instance.
- `GITLAB_ACCESS_TOKEN` - A Gitlab PAT with `read_api` and `read_user` permissions.
- `GITGUARDIAN_API_KEY` - A GitGuardian API Service Account Token with `members:read`, `members:write`, `teams:read`, `teams:write`, `sources:read` and `sources:write` permissions.

> [!TIP]
> If a Personal Access Token is used, the user who owns the PAT will be added
> to all teams when they're created. SATs are preferred for this reason.

Optional environment variables:

- `GITGUARDIAN_INSTANCE` - The URL of a self-hosted GitGuardian instance. Just the scheme and hostname: https://gitguardian.example.com
- `SEND_EMAIL` - Defines whether we should send an email to users when sending invitations
- `EXCLUDE_ADMIN` - Defines whether we should exclude admin users from sync
- `DEFAULT_INCIDENT_PERMISSION` - Defines the default incident permission level for team members, defaults to `can_edit`, it's value must be one of :
  - `can_view` : For read permissions
  - `can_edit` : For read and write permissions
  - `full_access` : For manager permissions

In order to ensure you have the correct configuration, you can run the following command to display the configuration:

```
python config.py
```

### Nested groups

Teams in GitGuardian will be created based on the name of the deepest group (not the **full path**) of every user's group.

This means that if a user is in `top-group / middle-group / bottom-group`, he will be added to the team `bottom-group` in GitGuardian.

### Invoking

Upon invocation, the script will sync teams and their perimeters from Gitlab to GitGuardian. It can be invoked like this:

```
python sync_gitlab.py
```
