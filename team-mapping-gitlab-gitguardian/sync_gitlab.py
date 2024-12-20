import logging
import requests

from typing import Iterable, TypedDict
from collections import defaultdict

from pygitguardian.models import (
    Invitation,
    Member,
    Team,
)

from gitguardian_client import (
    add_member_to_team,
    create_new_teams,
    delete_teams_by_name,
    list_all_sources,
    list_all_team_members,
    list_all_teams,
    list_all_members,
    list_all_invitations,
    list_team_sources,
    remove_team_member,
    send_invitation,
    send_team_invitation,
    update_team_source,
)
from config import CONFIG

logger = logging.getLogger(__name__)

GITLAB_USER_GRAPHQL_QUERY = """
query ($cursor: String, $admins: Boolean) {
    users(first: 100, after: $cursor, humans: true, admins: $admins) {
        pageInfo {
            endCursor
        }
        nodes {
            name
            emails {
                nodes {
                    email
                }
            }
            groups {
                nodes {
                    name
                    fullPath
                }
            }
        }
    }
}
"""

GITLAB_PROJECT_GRAPHQL_QUERY = """
query ($cursor: String) {
    projects(after: $cursor, first: 100) {
        pageInfo {
            endCursor
        }
        nodes {
            id
            name
            fullPath
            group {
                name
                fullPath
            }
        }
    }
}
"""

GitlabUser = TypedDict("GitlabUser", {"name": str, "email": str, "groups": list[str]})
GitlabProject = TypedDict(
    "GitlabProject", {"name": str, "group": str, "fullPath": str, "id": str}
)


def transform_gitlab_user(gitlab_user: dict) -> GitlabUser:
    """
    Transform the GraphQL representation of a User to a simpler dictionary
    """

    groups = gitlab_user.get("groups", {"nodes": []}) or {"nodes": []}
    return {
        "name": gitlab_user["name"],
        "email": next(
            (email["email"] for email in gitlab_user["emails"]["nodes"]), None
        ),
        "groups": [group["name"] for group in groups["nodes"]],
    }


def transform_gitlab_project(gitlab_project: dict) -> GitlabProject:
    group = gitlab_project["group"] or {"name": None}
    full_path = " / ".join(gitlab_project["fullPath"].split("/"))
    return {
        "id": gitlab_project["id"].split("/")[-1],
        "name": gitlab_project["name"],
        "fullPath": full_path,
        "group": group["name"],
    }


def flatten_user_groups(gitlab_users: list[GitlabUser]) -> set[str]:
    """
    Given a list of GitlabUser, return a flat list of all groups
    """

    return {group for user in gitlab_users for group in user["groups"]}


def fetch_gitlab_users() -> list[GitlabUser]:
    """
    Fetch all Gitlab users and their groups using GraphQL, iterate on pagination if needed
    """

    users = []

    url = f"{CONFIG.gitlab_url}/api/graphql"
    headers = {"Authorization": f"Bearer {CONFIG.gitlab_token}"}

    default_variables = {
        "admins": CONFIG.exclude_admin,
    }
    response = requests.post(
        url=url,
        json={"query": GITLAB_USER_GRAPHQL_QUERY, "variables": default_variables},
        headers=headers,
        timeout=60,
    )
    response.raise_for_status()

    data = response.json()
    end_cursor = data["data"]["users"]["pageInfo"]["endCursor"]
    users.extend(
        [transform_gitlab_user(user) for user in data["data"]["users"]["nodes"]]
    )

    while end_cursor:
        response = requests.post(
            url=f"{CONFIG.gitlab_url}/api/graphql",
            json={
                "query": GITLAB_USER_GRAPHQL_QUERY,
                "variables": {"cursor": end_cursor, **default_variables},
            },
            headers=headers,
        )
        response.raise_for_status()

        data = response.json()
        end_cursor = data["data"]["users"]["pageInfo"]["endCursor"]
        users.extend(
            [transform_gitlab_user(user) for user in data["data"]["users"]["nodes"]]
        )

    return users


def fetch_gitlab_projects() -> list[GitlabProject]:
    """
    Fetch all gitlab projects and their groups using GraphQL, iterate on pagination if needed
    """

    projects: list[GitlabProject] = []

    url = f"{CONFIG.gitlab_url}/api/graphql"
    headers = {"Authorization": f"Bearer {CONFIG.gitlab_token}"}

    default_variables = {
        "admins": CONFIG.exclude_admin,
    }
    response = requests.post(
        url=url,
        json={"query": GITLAB_PROJECT_GRAPHQL_QUERY, "variables": default_variables},
        headers=headers,
        timeout=60,
    )
    response.raise_for_status()

    data = response.json()
    end_cursor = data["data"]["projects"]["pageInfo"]["endCursor"]
    projects.extend(
        [
            transform_gitlab_project(project)
            for project in data["data"]["projects"]["nodes"]
            if project["group"] is not None
        ]
    )

    while end_cursor:
        response = requests.post(
            url=url,
            json={
                "query": GITLAB_PROJECT_GRAPHQL_QUERY,
                "variables": {"cursor": end_cursor, **default_variables},
            },
            headers=headers,
            timeout=60,
        )
        response.raise_for_status()

        data = response.json()
        end_cursor = data["data"]["projects"]["pageInfo"]["endCursor"]
        projects.extend(
            [
                transform_gitlab_project(project)
                for project in data["data"]["projects"]["nodes"]
                if project["group"] is not None
            ]
        )

    return projects


def list_group_members(gitlab_users: list[GitlabUser]) -> dict[str, set[str]]:
    """
    From the list of Gitlab users, reverse the mapping and create a dictionary
    where the keys are the groups' name and the values are the members' email
    """

    group_members = defaultdict(set)

    for user in gitlab_users:
        for group in user["groups"]:
            group_members[group].add(user["email"])

    return group_members


def synchronize_members(
    gitlab_group_members: dict[str, set[str]],
    gg_team_member_by_team_name: dict[str, list[tuple[int, Member]]],
    gg_members: list[Member],
    gg_teams: list[Team],
    gg_invitations: list[Invitation],
):
    """
    Using Gitlab group members and GitGuardian team members, synchronize the state of
    Gitlab group memberships with GitGuardian team memberships
    """

    members_by_emails = {member.email: member for member in gg_members}
    teams_by_names = {team.name: team for team in gg_teams}
    invitation_by_emails = {
        invitation.email: invitation for invitation in gg_invitations
    }

    for group_name, group_members in gitlab_group_members.items():
        if group_name in gg_team_member_by_team_name:

            team_members = gg_team_member_by_team_name[group_name]
            team_member_emails = {
                member.email
                for members in gg_team_member_by_team_name.values()
                for _, member in members
            }

            members_to_add = group_members - team_member_emails
            members_to_remove = team_member_emails - group_members

            gg_team = teams_by_names[group_name]
            team_id = gg_team.id
            for member in members_to_add:
                # If the member exists in GitGuardian, we can add him to the team
                if member in members_by_emails:
                    gg_member = members_by_emails[member]
                    add_member_to_team(gg_member, gg_team)

                # Else we need to send an invitation to the workspace and to the team
                else:
                    if member not in invitation_by_emails:
                        invitation = send_invitation(member)
                        invitation_by_emails[member] = invitation

                    send_team_invitation(invitation_by_emails[member], gg_team)

            # Members we could not find in Gitlab will be removed from the GitGuardian team
            for member in members_to_remove:
                team_member_id = next(
                    id
                    for id, team_member in team_members
                    if team_member.email == member
                )
                remove_team_member(team_id, team_member_id)


def infer_gitlab_email(
    gitlab_users: Iterable[GitlabUser], gg_members: Iterable[Member]
) -> list[GitlabUser]:
    """
    Given a list of gitlab users and a list of GitGuardian members, infer the Gitlab email
    from the users name by comparing it to the name of GitGuardian members
    If we can't fill the email, we skip the user
    """

    gg_member_names = {gg_member.name: gg_member for gg_member in gg_members}

    for gitlab_user in gitlab_users:
        if gitlab_user["name"] in gg_member_names and gitlab_user["email"] is None:
            gitlab_user["email"] = gg_member_names[gitlab_user["name"]].email

    return [gitlab_user for gitlab_user in gitlab_users if gitlab_user["email"]]


def get_gitlab_projects_per_group(
    gitlab_projects: Iterable[GitlabProject],
) -> dict[str, list[GitlabProject]]:
    """
    Transform a list of project into a map of group name to projects
    """

    projects_per_group: dict[str, list[GitlabProject]] = dict()

    for project in gitlab_projects:
        if project["group"] not in projects_per_group:
            projects_per_group[project["group"]] = []
        projects_per_group[project["group"]].append(project)

    return projects_per_group


def synchronize_sources(gg_teams: Iterable[Team]):
    """
    Given all GitGuardian teams, synchronize the list of sources attached
    to each team based on gitlab projects
    """

    gitlab_projects = fetch_gitlab_projects()
    gitlab_project_ids = {gitlab_project["id"] for gitlab_project in gitlab_projects}
    available_sources = list_all_sources()
    source_ids = {source.external_id for source in available_sources}

    gitlab_projects_per_group = get_gitlab_projects_per_group(gitlab_projects)

    unavailable_projects = gitlab_project_ids - source_ids
    if unavailable_projects:
        logger.warning(
            "The following projects are not available in GitGuardian:"
            + "\n - ".join(unavailable_projects)
        )

    all_sources_by_external_id = {
        source.external_id: source for source in available_sources
    }

    for team in gg_teams:
        team_projects = gitlab_projects_per_group.get(team.name, None)
        if team_projects is None:
            continue

        team_sources = list_team_sources(team)

        project_ids = {
            project["id"]
            for project in gitlab_projects_per_group[team.name]
            if project["id"] not in unavailable_projects
        }
        team_source_ids = {source.external_id for source in team_sources}

        sources_to_add = [
            all_sources_by_external_id[id].id for id in (project_ids - team_source_ids)
        ]
        sources_to_delete = [
            all_sources_by_external_id[id].id for id in (team_source_ids - project_ids)
        ]

        update_team_source(team, sources_to_add, sources_to_delete)


def main():
    gg_teams: list[Team] = list_all_teams()
    gg_members: list[Member] = list_all_members()
    gg_invitations: list[Invitation] = list_all_invitations()

    gitlab_users = infer_gitlab_email(fetch_gitlab_users(), gg_members)
    gitlab_groups = set(flatten_user_groups(gitlab_users))

    to_delete_teams = set([team.name for team in gg_teams]) - gitlab_groups
    to_add_teams = gitlab_groups - set([team.name for team in gg_teams])
    created_teams = create_new_teams(to_add_teams)
    delete_teams_by_name(gg_teams, to_delete_teams)

    available_teams = [
        team for team in gg_teams if team.name not in to_delete_teams
    ] + created_teams
    current_team_members = list_all_team_members(available_teams, gg_members)
    group_members = list_group_members(gitlab_users)

    synchronize_sources(available_teams)

    synchronize_members(
        group_members,
        current_team_members,
        gg_members,
        available_teams,
        gg_invitations,
    )


if __name__ == "__main__":
    logging.basicConfig(level=CONFIG.logger_level)
    main()
