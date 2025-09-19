import logging
from collections import defaultdict
from typing import Iterable

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
    team_gitlab_id,
    update_team_source,
)
from gitlab_client import fetch_gitlab_projects, fetch_gitlab_users
from util import (
    GitlabGroup,
    GitlabProject,
    GitlabUserGroup,
    team_description_from_group,
)

logger = logging.getLogger(__name__)


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
                        "fullName": group["fullName"],
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


def list_group_members(
    gitlab_users: list[GitlabUserGroup],
) -> dict[str, set[str | None]]:
    """
    From the list of Gitlab users, reverse the mapping and create a dictionary
    where the keys are the groups' full name and the values are the members' email
    """

    group_members = defaultdict(set)

    for user in gitlab_users:
        for group in user["groups"]:
            group_members[group["fullName"]].add(user["email"])

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
                if not member:
                    continue
                # If the member exists in GitGuardian, we can add him to the team
                if member in members_by_emails:
                    gg_member = members_by_emails[member]
                    add_member_to_team(gg_member, gg_team)

                # Else we need to send an invitation to the workspace and to the team
                else:
                    if member not in invitation_by_emails:
                        if invitation := send_invitation(member):
                            invitation_by_emails[member] = invitation

                    if member in invitation_by_emails:
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

    projects_per_group: dict[str, list[GitlabProject]] = {}

    for project in gitlab_projects:
        if project["group"] not in projects_per_group:
            projects_per_group[project["group"]] = []
        projects_per_group[project["group"]].append(project)

    return projects_per_group


def synchronize_sources(
    gg_teams: Iterable[Team], sources_by_team_id: dict[int, list[Source]]
):
    """
    Given all GitGuardian teams, synchronize the list of sources attached
    to each team based on gitlab projects
    """

    gitlab_projects = fetch_gitlab_projects()
    gitlab_project_ids = {gitlab_project["id"] for gitlab_project in gitlab_projects}
    sources_by_external_id = {
        source.external_id: source for source in list_all_sources()
    }
    source_external_ids = set(sources_by_external_id.keys())

    gitlab_projects_per_group = get_gitlab_projects_per_group(gitlab_projects)

    unmonitored_projects = gitlab_project_ids - source_external_ids
    if unmonitored_projects:
        logger.warning(
            "The following projects are not monitored by GitGuardian:"
            + "\n - ".join(unmonitored_projects)
        )

    def diff_sources(
        team: Team,
        gitlab_id: str,
    ) -> tuple[list[int], list[int]]:
        team_sources = sources_by_team_id[team.id]

        project_ids = {
            project["id"]
            for project in gitlab_projects_per_group[gitlab_id]
            if project["id"] not in unmonitored_projects
        }
        team_source_ids = {source.external_id for source in team_sources}

        sources_to_add = [
            sources_by_external_id[id].id for id in (project_ids - team_source_ids)
        ]
        sources_to_delete = [
            sources_by_external_id[id].id for id in (team_source_ids - project_ids)
        ]

        return sources_to_add, sources_to_delete

    for team in gg_teams:
        if gitlab_id := team_gitlab_id(team):
            team_projects = gitlab_projects_per_group.get(gitlab_id, None)
            if team_projects is None:
                logger.debug(
                    "No match for team: %d - %s (%s)",
                    team.id,
                    team.name,
                    team.description,
                )
                continue
            sources_to_add, sources_to_delete = diff_sources(team, gitlab_id)
            if sources_to_add or sources_to_delete:
                update_team_source(team, sources_to_add, sources_to_delete)
        else:
            logger.debug(
                "No GitLab ID for team: %d - %s (%s)",
                team.id,
                team.name,
                team.description,
            )
            continue


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
        if member_email:
            send_invitation(member_email)


def create_team_from_group(group: GitlabGroup) -> Team:
    """
    Given a Gitlab group, create the corresponding GitGuardian team
    """
    payload = CreateTeam(
        group["fullName"],
        description=team_description_from_group(group),
    )
    response = CONFIG.client.create_team(payload)

    if isinstance(response, Detail):
        raise RuntimeError(
            f"Unable to create team {group['fullName']}: {response.detail}"
        )

    logger.info(f"Successfully created team {group['fullName']}")
    return response


def rename_team_from_group(team: Team, group: GitlabGroup) -> Team:
    """
    Given a GitGuardian team and a Gitlab group, rename the GitGuardian team to
    match the Gitlab group full path
    """
    payload = UpdateTeam(
        team.id,
        name=group["fullName"],
        description=team_description_from_group(group),
    )
    response = CONFIG.client.update_team(payload)

    if isinstance(response, Detail):
        raise RuntimeError(
            f"Unable to rename team {group['fullName']}: {response.detail}"
        )

    logger.info(f"Successfully renamed team from {team.name} to {group['fullName']}")
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

    for group_id in teams_to_add:
        group = groups_by_id[group_id]
        teams_by_external_id[group["id"]] = create_team_from_group(
            groups_by_id[group_id]
        )
    for group_id in teams_to_remove:
        delete_team(teams_by_external_id[group_id])

    teams_by_external_id = {
        group_id: team
        for group_id, team in teams_by_external_id.items()
        if group_id not in teams_to_remove
    }

    for team in team_intersection:
        gg_team = teams_by_external_id[team]
        group = groups_by_id[team]

        if gg_team.name != group["fullName"]:
            teams_by_external_id[group["id"]] = rename_team_from_group(gg_team, group)

    return list(teams_by_external_id.values())


def main():
    logger.info("Fetching GitGuardian data")
    gg_teams, teams_by_external_id = list_all_teams()
    gg_members = list_all_members()
    gg_source_by_team_id = list_sources_by_team_id(gg_teams)

    logger.info("Fetching GitLab data")
    gitlab_users = infer_gitlab_email(fetch_gitlab_users(), gg_members)
    gitlab_user_emails = {gitlab_user["email"] for gitlab_user in gitlab_users}
    gitlab_group_by_id = map_gitlab_groups(gitlab_users)

    logger.info("Synchronizing GitGuardian teams")
    available_teams = synchronize_teams(teams_by_external_id, gitlab_group_by_id)

    # Delete or deactivate members we cannot find in gitlab anymore
    members_to_delete = [
        member for member in gg_members if member.email not in gitlab_user_emails
    ]
    logger.info("Removing members from GitGuardian")
    remove_members(members_to_delete)

    member_ids_to_delete = {member.id for member in members_to_delete}
    gg_members = [
        member for member in gg_members if member.id not in member_ids_to_delete
    ]

    logger.info("Inviting new members to GitGuardian")
    invite_new_members(gitlab_users, gg_members)

    logger.info("Synchronizing GitGuardian team perimeters")
    synchronize_sources(available_teams, gg_source_by_team_id)

    gg_invitations = list_all_invitations()
    invitations_to_delete = [
        invitation
        for invitation in gg_invitations
        if invitation.email not in gitlab_user_emails
    ]
    invitation_ids_to_delete = {invitation.id for invitation in invitations_to_delete}
    logger.info("Removing invitations from GitGuardian")
    delete_invitations(invitations_to_delete)

    gg_invitations = [
        invitation
        for invitation in gg_invitations
        if invitation.id not in invitation_ids_to_delete
    ]
    logger.info("Synchronizing GitGuardian team members")
    synchronize_team_members(gitlab_users, gg_members, available_teams, gg_invitations)


if __name__ == "__main__":
    logging.basicConfig(level=CONFIG.logger_level)
    main()
