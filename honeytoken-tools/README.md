
# Disseminate honeytokens

Deploy honeytokens - decoy AWS keys - in your code repositories to act as an alarm system, and be alerted in case of intrusion or leak! Learn more about Honeytoken [here](https://docs.gitguardian.com/honeytoken/home).

This repository contains a script called `disseminate_honeytokens.py` which will help you deploy honeytokens at scale in your codebase. For each of the targeted repositories, this tool will create a new branch and a pull request to insert a unique honeytoken.

Example:

```
disseminate_honeytokens.py --vcs github --repo-names Example/test
```

This script can create pull request to one of the following VCS:

- GitHub
- GitHub Enterprise
- GitLab
- Azure DevOps
- BitBucket server

**Warning:** To use the script, you must set `VCS_TOKEN` and `GITGUARDIAN_TOKEN` environment variables. See more in 
the sections below.

# Prerequisites

## Script dependencies

This script requires the `requests` library to be installed. You can install it using pip.

```
pip install requests
```

## GitGuardian Personal Access Token

Generating the honeytoken and a plausible context is done using the
[GitGuardian Honeytoken API](https://api.gitguardian.com/docs#tag/Honeytokens/operation/create-honeytoken-with-context), 
for which you must have a GitGuardian account and a manager role. 

You'll need to create a GitGuardian [Personal Access Token](https://docs.gitguardian.com/api-docs/personal-access-tokens)
with `honeytokens:write` scope selected. Use environment variable `GITGUARDIAN_TOKEN` to provide it.

If you use GitGuardian Enterprise Self-Hosted, you will also need to specify the url of your GitGuardian instance 
via environment variable `GITGUARDIAN_URL` or as a script parameter.

## VCS Personal Access Token

To use any of the VCS you will need to have an access token with the write permissions on the repositories where you 
want to disseminate honeytokens. You should use environment variable `VCS_TOKEN` to provide your access token.

If the VCS instance is self-hosted, you will need to specify url of your GitHub instance via environment 
variable `VCS_URL` or as a script parameter.

### **GitHub or GitHub Enterprise**

Create a [GitHub Personal Access Token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens). Make sure that you give the token write permissions on the repository where you want to disseminate honeytokens: 

- If you use classic GitHub personal access tokens, you must choose `repo` scope.
- If you use fine-grained personal access tokens, you must select the repositories where you want to disseminate honeytokens 
and give them `contents:write` and `pull_requests:write` permissions.

If you use GitHub Enterprise version, you will also need to specify url of your GitHub instance via environment variable 
`VCS_URL` or as a script parameter.

```
disseminate_honeytokens.py --vcs github --repo-names Example/test1 Example/test2 [--vcs-url VCS_URL] [--gitguardian-url GITGUARDIAN_URL]
```

### Gitlab

Create a [Gitlab personal access token](https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html) with an
`api` scope.

To disseminate honeytokens in Gitlab projects, provide full path to the project (with the namespace) 
via `repo-names` parameter:

```
python disseminate_honeytokens.py --vcs gitlab --repo-names namespace/project_name [--vcs-url VCS_URL] [--gitguardian-url GITGUARDIAN_URL]
```

### Azure DevOps

Create an [Azure DevOps personal access token](https://learn.microsoft.com/en-us/azure/devops/organizations/accounts/use-personal-access-tokens-to-authenticate?view=azure-devops&tabs=Windows)
with `Code:write` and `Analytics:read` scopes.

To disseminate honeytokens in Azure DevOps repositories, provide full path to the repositories (including 
organization and project names separated by `/`) via `repo-names` parameter:
```
python disseminate_honeytokens.py --vcs ado --repo-names organization/project/repository [--vcs-url VCS_URL] [--gitguardian-url GITGUARDIAN_URL]
```

### BitBucket Server

Create an [BitBucket Server access token](https://confluence.atlassian.com/bitbucketserver/http-access-tokens-939515499.html)
with `Project read` and `Repository write` permissions.

To disseminate honeytokens in BitBucket Server repositories, provide full path to the repositories (including project name) 
via `repo-names` parameter:
```
python disseminate_honeytokens.py --vcs bitbucket --repo-names project/repository [--vcs-url VCS_URL] [--gitguardian-url GITGUARDIAN_URL]
```

**Warning:** This script does not support projects and repositories hosted on Bitbucket Cloud (bitbucket.org).