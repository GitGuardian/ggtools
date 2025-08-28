import json
import logging
from collections import defaultdict
from typing import Iterable, TypedDict

import requests
from email_validator import EmailNotValidError, validate_email
from pygitguardian.models import (
    CreateTeam,
    Detail,
    Invitation,
    Member,
    Source,
    Team,
    UpdateTeam,
)

from config import CONFIG
from gitguardian_client import (
    add_member_to_team,
    delete_invitations,
    delete_team,
    list_all_invitations,
    list_all_members,
    list_all_sources,
    list_all_team_members,
    list_all_teams,
    list_sources_by_team_id,
    list_team_invitations,
    remove_members,
    remove_team_invitation,
    remove_team_member,
    send_invitation,
    send_team_invitation,
    update_team_source,
)

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
                    id
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

GitlabUserGroup = TypedDict(
    "GitlabUserGroup",
    {"name": str, "email": str | None, "groups": list[dict[str, str | int]]},
)
GitlabUser = TypedDict("GitlabUser", {"name": str, "email": str})
GitlabGroup = TypedDict(
    "GitlabGroup", {"id": str, "fullPath": str, "users": list[GitlabUser]}
)
GitlabProject = TypedDict(
    "GitlabProject", {"name": str, "group": str, "fullPath": str, "id": str}
)


def get_valid_email(emails: Iterable[str]) -> str | None:
    """
    Get the first valid email address from a list of potential email addresses.
    """
    for email in emails:
        try:
            emailinfo = validate_email(email, check_deliverability=False)
            return emailinfo.normalized
        except EmailNotValidError as e:
            logger.debug(
                "Email validation failed - email: %s, error: %s",
                email,
                str(e),
            )
    return None


def transform_gitlab_user(gitlab_user: dict) -> GitlabUserGroup:
    """
    Transform the GraphQL representation of a User to a simpler dictionary
    """

    groups = gitlab_user.get("groups", {}).get("nodes", [])
    for group in groups:
        group["fullPath"] = " / ".join(group["fullPath"].split("/"))

    return {
        "name": gitlab_user["name"],
        "email": get_valid_email(e["email"] for e in gitlab_user["emails"]["nodes"]),
        "groups": groups,
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


def map_gitlab_groups(
    gitlab_users: list[GitlabUserGroup],
) -> dict[str, GitlabGroup]:
    """
    Given a list of users, construct a mapping from a Gitlab id to GitlabGroup
    """

    gitlab_group_by_id: dict[str, GitlabGroup] = {}

    selectors = {"id": gitlab_group_by_id}

    for user in gitlab_users:
        for group in user["groups"]:
            for selector, res in selectors.items():
                if group[selector] not in res:
                    res[group[selector]] = {
                        "id": group["id"],
                        "fullPath": group["fullPath"],
                        "users": [],
                    }

                group_users = res[group[selector]]["users"]
                group_users.append(
                    {
                        "email": user["email"],
                        "name": user["name"],
                    }
                )

    return gitlab_group_by_id


def fetch_gitlab_users() -> list[GitlabUserGroup]:
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
            group_members[group["fullPath"]].add(user["email"])

    return group_members


def synchronize_team_members(
    gitlab_users: list[GitlabUserGroup],
    gg_members: list[Member],
    gg_teams: list[Team],
    gg_invitations: list[Invitation],
):
    """
    Using Gitlab group members and GitGuardian team members, synchronize the state of
    Gitlab group memberships with GitGuardian team memberships
    """

    gitlab_group_members = list_group_members(gitlab_users)
    gg_team_member_by_team_name = list_all_team_members(gg_teams, gg_members)

    members_by_emails = {member.email: member for member in gg_members}
    teams_by_names = {team.name: team for team in gg_teams}
    invitation_by_emails = {
        invitation.email: invitation for invitation in gg_invitations
    }
    invitation_by_id = {invitation.id: invitation for invitation in gg_invitations}

    for group_name, group_members in gitlab_group_members.items():
        gg_team = teams_by_names[group_name]

        if group_name in gg_team_member_by_team_name:
            team_invitations = list_team_invitations(gg_team)

            team_members = gg_team_member_by_team_name[group_name]
            team_member_emails = {
                member.email
                for members in gg_team_member_by_team_name.values()
                for _, member in members
            }

            members_to_add = group_members - team_member_emails
            members_to_remove = team_member_emails - group_members

            invitations_to_remove = [
                team_invitation
                for team_invitation in team_invitations
                if invitation_by_id[team_invitation.invitation_id].email
                not in group_members
            ]

            for team_invitation in invitations_to_remove:
                remove_team_invitation(
                    gg_team,
                    team_invitation.id,
                    invitation_by_id[team_invitation.invitation_id].email,
                )

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
                    (
                        id
                        for id, team_member in team_members
                        if team_member.email == member
                    ),
                    None,
                )
                if team_member_id:
                    remove_team_member(gg_team, team_member_id)


def infer_gitlab_email(
    gitlab_users: Iterable[GitlabUserGroup], gg_members: Iterable[Member]
) -> list[GitlabUserGroup]:
    """
    Given a list of gitlab users and a list of GitGuardian members, infer the Gitlab email
    from the users name by comparing it to the name of GitGuardian members
    If we can't fill the email, we skip the user
    """

    gg_member_names = {gg_member.name: gg_member for gg_member in gg_members}

    gitlab_users_with_email = []

    for gitlab_user in gitlab_users:
        if gitlab_user["email"] is None:
            if gitlab_user["name"] in gg_member_names:
                gitlab_user["email"] = gg_member_names[gitlab_user["name"]].email
            else:
                logger.warning(
                    "No email nor name match for GitLab user %s", gitlab_user["name"]
                )
                continue
        gitlab_users_with_email.append(gitlab_user)

    return gitlab_users_with_email


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


def synchronize_sources(
    gg_teams: Iterable[Team], sources_by_team_id: dict[id, list[Source]]
):
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

        team_sources = sources_by_team_id[team.id]

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


def invite_new_members(
    gitlab_users: Iterable[GitlabUserGroup], gg_members: Iterable[Member]
):
    """
    Invite missing members to the workspace
    """

    all_invitations = list_all_invitations()
    gitlab_users_by_email = {
        gitlab_user["email"]: gitlab_user for gitlab_user in gitlab_users
    }
    members_to_invite = (
        set(gitlab_users_by_email.keys())
        - {member.email for member in gg_members}
        - {invitation.email for invitation in all_invitations}
    )

    for member_email in members_to_invite:
        send_invitation(member_email)


def create_team_from_group(group: GitlabGroup) -> Team:
    """
    Given a Gitlab group, create the corresponding GitGuardian team
    """
    metadata = {key: value for key, value in group.items() if key != "users"}
    payload = CreateTeam(group["fullPath"], description=json.dumps(metadata))
    response = CONFIG.client.create_team(payload)

    if isinstance(response, Detail):
        raise RuntimeError(
            f"Unable to create team {group['fullPath']}: {response.detail}"
        )

    logger.info(f"Successfully created team {group['fullPath']}")
    return response


def rename_team_from_group(team: Team, group: GitlabGroup) -> Team:
    """
    Given a GitGuardian team and a Gitlab group, rename the GitGuardian team to
    match the Gitlab group full path
    """
    metadata = {key: value for key, value in group.items() if key != "users"}
    payload = UpdateTeam(
        team.id, name=group["fullPath"], description=json.dumps(metadata)
    )
    response = CONFIG.client.update_team(payload)

    if isinstance(response, Detail):
        raise RuntimeError(
            f"Unable to rename team {group['fullPath']}: {response.detail}"
        )

    logger.info(f"Successfully renamed team from {team.name} to {group['fullPath']}")
    return response


def synchronize_teams(
    teams_by_external_id: dict[str, Team],
    groups_by_id: dict[str, GitlabGroup],
) -> list[Team]:
    """
    Using stored external ids, we will:
        - Create teams that don't exist
        - Delete teams we cannot find
        - Rename teams that have been renamed on Gitlab
    """

    teams_to_add = set(groups_by_id.keys()) - set(teams_by_external_id.keys())
    teams_to_remove = set(teams_by_external_id.keys()) - set(groups_by_id.keys())
    team_intersection = set(teams_by_external_id.keys()) & set(groups_by_id.keys())

    for team in teams_to_add:
        group = groups_by_id[team]
        teams_by_external_id[group["id"]] = create_team_from_group(groups_by_id[team])
    for team in teams_to_remove:
        delete_team(teams_by_external_id[team])

    teams_by_external_id = {
        id: team
        for id, team in teams_by_external_id.items()
        if id not in teams_to_remove
    }

    for team in team_intersection:
        gg_team = teams_by_external_id[team]
        group = groups_by_id[team]

        if gg_team.name != group["fullPath"]:
            teams_by_external_id[group["fullPath"]] = rename_team_from_group(
                gg_team, group
            )

    return list(teams_by_external_id.values())


def main():
    gg_teams, teams_by_external_id = list_all_teams()
    gg_members = list_all_members()
    gg_source_by_team_id = list_sources_by_team_id(gg_teams)

    gitlab_users = infer_gitlab_email(fetch_gitlab_users(), gg_members)
    gitlab_user_emails = {gitlab_user["email"] for gitlab_user in gitlab_users}
    gitlab_group_by_id = map_gitlab_groups(gitlab_users)

    available_teams = synchronize_teams(teams_by_external_id, gitlab_group_by_id)

    # Delete or deactivate members we cannot find in gitlab anymore
    members_to_delete = [
        member for member in gg_members if member.email not in gitlab_user_emails
    ]
    remove_members(members_to_delete)

    member_ids_to_delete = {member.id for member in members_to_delete}
    gg_members = [
        member for member in gg_members if member.id not in member_ids_to_delete
    ]

    invite_new_members(gitlab_users, gg_members)

    synchronize_sources(available_teams, gg_source_by_team_id)

    gg_invitations = list_all_invitations()
    invitations_to_delete = [
        invitation
        for invitation in gg_invitations
        if invitation.email not in gitlab_user_emails
    ]
    invitation_ids_to_delete = {invitation.id for invitation in invitations_to_delete}
    delete_invitations(invitations_to_delete)

    gg_invitations = [
        invitation
        for invitation in gg_invitations
        if invitation.id not in invitation_ids_to_delete
    ]
    synchronize_team_members(gitlab_users, gg_members, available_teams, gg_invitations)


if __name__ == "__main__":
    logging.basicConfig(level=CONFIG.logger_level)
    main()
