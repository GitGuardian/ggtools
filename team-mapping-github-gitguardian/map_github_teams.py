from github import Auth, Github, GithubRetry

from config import Config
from gitguardian_client import GitGuardianClient


def github_team_nested_name(team):
    if team.parent:
        parent_name = github_team_nested_name(team.parent)
        return f"{parent_name} > {team.name}"
    return team.name


def team_has_maintainer_permission(team, repo):
    permissions = team.get_repo_permission(repo)
    if permissions.maintain or permissions.admin:
        return True
    return False


def main(config):
    gitguardian = (
        GitGuardianClient(
            api_token=config.gitguardian_token,
            instance=config.gitguardian_instance,
        )
        .ensure_healthy()
        .ensure_scopes({"teams:read", "teams:write", "sources:read"})
        .load_teams()
        .load_sources()
    )

    github_params = {
        "auth": Auth.Token(config.github_token),
        "retry": GithubRetry(),
    }

    if config.github_instance is not None:
        github_params["base_url"] = f"{config.github_instance}/api/v3"

    github_org = Github(**github_params).get_organization(config.github_org)

    for team in github_org.get_teams():
        nested_name = github_team_nested_name(team)
        print(f"Processing team: {nested_name}")
        gg_team = gitguardian.create_or_sync_team(
            display_name=f"{github_org.login} / {nested_name}",
            github_id=team.id,
            github_description=team.description,
        )
        repo_ids = set(
            r.id for r in team.get_repos() if team_has_maintainer_permission(team, r)
        )
        print(f"    Repos: {repo_ids}")
        gg_team.update_sources(github_repo_ids=repo_ids)


if __name__ == "__main__":
    main(Config())
