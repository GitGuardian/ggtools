import logging
import json
from json import JSONDecodeError
from pygitguardian.models import Team, TeamMember, TeamInvitation, Member, Invitation
from github.Team import Team as GHTeam
from github.Repository import Repository as GHRepository
from gitguardian_calls import (
    list_all_gg_invitations,
    list_all_gg_members,
    list_all_gg_teams,
    list_all_gg_sources,
    list_team_sources,
    list_team_invitations,
    list_team_members,
    add_team_invitation,
    delete_team_invitation,
    create_team,
    update_team,
    add_team_member,
    delete_team,
    delete_team_member,
    update_team_sources,
    invite_user,
)
from github_calls import (
    IdpNotImplementedException,
    list_github_saml_users,
    list_github_user_teams,
    list_github_users,
)
from config import CONFIG


logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=CONFIG.logger_level)

    gg_teams_by_gh_id, gh_teams_by_id = sync_teams()

    sync_team_perimeters(gh_teams_by_id, gg_teams_by_gh_id)

    sync_users(gg_teams_by_gh_id)

    sync_team_memberships(gg_teams_by_gh_id)


def sync_teams() -> dict[int, Team]:
    github_org = CONFIG.github_client.get_organization(CONFIG.github_org)
    gh_teams_by_id = {team.id: team for team in github_org.get_teams()}
    gg_teams_by_gh_id = list_gg_teams_by_gh_id()

    update_existing_teams(gg_teams_by_gh_id, gh_teams_by_id)
    delete_extra_teams(gg_teams_by_gh_id, gh_teams_by_id)
    create_unknown_teams(gg_teams_by_gh_id, gh_teams_by_id)

    return gg_teams_by_gh_id, gh_teams_by_id


def list_gg_teams_by_gh_id():
    all_teams = list_all_gg_teams()
    org_teams_by_external_id = {}

    for team in all_teams:
        try:
            team._parsed_description = json.loads(team.description)
            team._member_ids = set()
            team._invitation_ids = set()
        except (JSONDecodeError, TypeError, ValueError):
            continue

        if (
            team._parsed_description["vcs"] == "github"
            and team._parsed_description["instance"] == CONFIG.github_instance
            and team._parsed_description["org_name"] == CONFIG.github_org
        ):
            org_teams_by_external_id[team._parsed_description["external_id"]] = team

    return org_teams_by_external_id


def update_existing_teams(
    gg_teams_by_gh_id: dict[int, Team],
    gh_teams_by_id: dict[int, GHTeam],
) -> None:
    existing_team_ids = set(gg_teams_by_gh_id.keys()) & set(gh_teams_by_id.keys())

    for gh_id in existing_team_ids:
        gg_team = gg_teams_by_gh_id[gh_id]
        gh_team = gh_teams_by_id[gh_id]

        if gg_team.name != github_team_nested_name(gh_team):
            gg_team.name = gh_team.name
            update_team(team_id=gg_team.id, name=gh_team.name)


def create_unknown_teams(
    gg_teams_by_gh_id: dict[int, Team],
    gh_teams_by_id: dict[int, GHTeam],
) -> None:
    unknown_team_ids = set(gh_teams_by_id.keys()) - set(gg_teams_by_gh_id.keys())

    for gh_id in unknown_team_ids:
        gh_team = gh_teams_by_id[gh_id]
        name = github_team_nested_name(gh_team)
        description = {
            "vcs": "github",
            "instance": CONFIG.github_instance,
            "org_name": CONFIG.github_org,
            "external_id": gh_id,
        }
        gg_team = create_team(name=name, description=json.dumps(description))
        gg_team._parsed_description = description
        gg_team._member_ids = set()
        gg_team._invitation_ids = set()
        gg_teams_by_gh_id[gh_id] = gg_team


def delete_extra_teams(
    gg_teams_by_gh_id: dict[int, Team],
    gh_teams_by_id: dict[int, GHTeam],
) -> None:
    extra_teams_ids = set(gg_teams_by_gh_id.keys()) - set(gh_teams_by_id.keys())

    for gh_id in extra_teams_ids:
        gg_team = gg_teams_by_gh_id[gh_id]
        delete_team(gg_team)
        del gg_teams_by_gh_id[gh_id]


def sync_team_perimeters(gh_teams_by_id: dict[int, GHTeam], gg_teams_by_gh_id: dict[int, Team]):
    """Synchronize the perimeter of the team to the repositories it has access on GitHub."""
    gg_sources_by_gh_id = {int(source.external_id): source for source in list_all_gg_sources()}

    for gh_id, gh_team in gh_teams_by_id.items():
        gg_team = gg_teams_by_gh_id[gh_id]

        current_gh_repo_ids = set(
            repo.id for repo in gh_team.get_repos() if team_has_maintainer_permission(gh_team, repo)
        )
        old_gh_repo_ids = {int(source.external_id) for source in list_team_sources(gg_team)}

        gh_repo_ids_to_add = current_gh_repo_ids - old_gh_repo_ids
        gh_repo_ids_to_remove = old_gh_repo_ids - current_gh_repo_ids

        sources_to_add = [
            gg_sources_by_gh_id[gh_repo_id].id
            for gh_repo_id in gh_repo_ids_to_add
            if gg_sources_by_gh_id.get(gh_repo_id)
        ]
        sources_to_remove = [
            gg_sources_by_gh_id[gh_repo_id].id
            for gh_repo_id in gh_repo_ids_to_remove
            if gg_sources_by_gh_id.get(gh_repo_id)
        ]

        update_team_sources(
            gg_team=gg_team,
            sources_to_add=sources_to_add,
            sources_to_remove=sources_to_remove,
        )


def sync_users(gg_teams_by_gh_id: dict[int, Team]):
    """Synchronize the users and their teams."""
    gg_invitations_by_email = {invitation.email: invitation for invitation in list_all_gg_invitations()}
    gg_members_by_email = {member.email: member for member in list_all_gg_members()}

    try:
        gh_users = list(list_github_saml_users())
    except IdpNotImplementedException:
        logger.info("No IDP set up on GitHub, falling back on the list of organization members.")
        gh_users = list(list_github_users())

    for gh_user in gh_users:
        gg_user = None
        if (gh_user.email in gg_members_by_email.keys()):
            gg_user = gg_members_by_email.get(gh_user.email)
        elif (gh_user.email in gg_invitations_by_email.keys()):
            gg_user = gg_invitations_by_email.get(gh_user.email)
        elif gh_user.email not in CONFIG.email_blacklist:
            gg_user = invite_user(gh_user.email)

        if gg_user is None:
            continue

        user_gh_team_ids = set(list_github_user_teams(gh_user))
        user_gg_teams = [gg_teams_by_gh_id[gh_id] for gh_id in user_gh_team_ids]

        for team in user_gg_teams:
            if isinstance(gg_user, Member):
                team._member_ids.add(gg_user.id)
            elif isinstance(gg_user, Invitation):
                team._invitation_ids.add(gg_user.id)


def sync_team_memberships(gg_teams_by_gh_id: dict[int, Team]):
    for team in gg_teams_by_gh_id.values():
        existing_team_members = list(list_team_members(team))
        remove_extra_team_members(team, existing_team_members)
        add_missing_team_members(team, existing_team_members)

        existing_team_invitations = list(list_team_invitations(team))
        remove_extra_team_invitations(team, existing_team_invitations)
        add_missing_team_invitations(team, existing_team_invitations)


def remove_extra_team_members(team: Team, existing_team_members: list[TeamMember]):
    extra_team_members = [
        team_member
        for team_member in existing_team_members
        if team_member.member_id not in team._member_ids
    ]

    for team_member in extra_team_members:
        delete_team_member(team, team_member)


def add_missing_team_members(team: Team, existing_team_members: list[TeamMember]):
    existing_member_ids = [team_member.member_id for team_member in existing_team_members]
    missing_member_ids = [
        member_id
        for member_id in team._member_ids
        if member_id not in existing_member_ids
    ]

    for member_id in missing_member_ids:
        add_team_member(team, member_id)


def remove_extra_team_invitations(team: Team, existing_team_invitations: list[TeamInvitation]):
    extra_team_invitations = [
        team_invitation
        for team_invitation in existing_team_invitations
        if team_invitation.invitation_id not in team._invitation_ids
    ]

    for team_invitation in extra_team_invitations:
        delete_team_invitation(team, team_invitation)


def add_missing_team_invitations(team: Team, existing_team_invitations: list[TeamInvitation]):
    existing_invitation_ids = [team_invite.invitation_id for team_invite in existing_team_invitations]
    missing_invitation_ids = [
        invitation_id
        for invitation_id in team._invitation_ids
        if invitation_id not in existing_invitation_ids
    ]

    for invitation_id in missing_invitation_ids:
        add_team_invitation(team, invitation_id)


def github_team_nested_name(team: GHTeam) -> str:
    if team.parent:
        parent_name = github_team_nested_name(team.parent)
        return f"{parent_name} > {team.name}"
    return team.name


def team_has_maintainer_permission(team: GHTeam, repo: GHRepository) -> bool:
    permissions = team.get_repo_permission(repo)
    if not permissions:
        return False

    if permissions.maintain or permissions.admin:
        return True
    return False


if __name__ == "__main__":
    main()
