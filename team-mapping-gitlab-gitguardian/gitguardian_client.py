import logging
from collections import defaultdict
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

from pygitguardian.models import (
    AccessLevel,
    CreateInvitation,
    CreateInvitationParameters,
    CreateTeam,
    CreateTeamInvitation,
    CreateTeamMember,
    CreateTeamMemberParameters,
    DeleteMemberParameters,
    Detail,
    IncidentPermission,
    Invitation,
    Member,
    Source,
    SourceParameters,
    Team,
    TeamInvitation,
    TeamsParameters,
    UpdateMember,
    UpdateTeamSource,
)
from pygitguardian.models_utils import CursorPaginatedResponse, PaginationParameter

from config import CONFIG
from util import team_gitlab_id

logger = logging.getLogger(__name__)


def get_cursor(url: str) -> str | None:
    """
    Extract cursor query parameter from a URL
    """
    parsed_url = urlparse(url)

    query_params = parse_qs(parsed_url.query)
    return query_params.get("cursor", [None])[0]


def pagination_max_results(
    method: Any,
    parameter_cls=PaginationParameter,
    additional_parameters: dict[str, str | bool] | None = None,
) -> list:
    """
    Iterate over all pages of a paginated response from GitGuardian API

    Use Parameters inheritance from PaginationParameter to loop
    on all `list` methods
    """

    if additional_parameters is None:
        additional_parameters = {}

    pagination_parameters = parameter_cls(
        per_page=CONFIG.pagination_size, **additional_parameters
    )
    paginated_response: CursorPaginatedResponse | Detail = method(
        parameters=pagination_parameters
    )
    if isinstance(paginated_response, Detail):
        raise RuntimeError(
            f"There was an error in the initial paginated call: {paginated_response.detail}"
        )

    data = paginated_response.data
    next = paginated_response.next

    while next and (cursor := get_cursor(next)):
        pagination_parameters = parameter_cls(
            cursor=cursor, per_page=CONFIG.pagination_size, **additional_parameters
        )
        paginated_response = method(parameters=pagination_parameters)

        if isinstance(paginated_response, Detail):
            raise RuntimeError(
                f"There was an error fetching the next page: {paginated_response.detail}"
            )

        data.extend(paginated_response.data)
        next = paginated_response.next

    return data


def list_all_team_members(
    all_teams: list[Team], all_members: list[Member]
) -> dict[str, list[tuple[int, Member]]]:
    """
    List all team members for all teams from GitGuardian, map them by team name
    to a team_member_id and member model tuple
    """

    id_to_member = {member.id: member for member in all_members}
    all_team_members: dict[str, list[tuple[int, Member]]] = {}
    for team in all_teams:
        all_team_members[team.name] = []
        list_team_members = lambda parameters: CONFIG.client.list_team_members(
            team.id, parameters=parameters
        )
        team_members = pagination_max_results(list_team_members)
        for team_member in team_members:
            if team_member.member_id in id_to_member:
                all_team_members[team.name].append(
                    (team_member.id, id_to_member[team_member.member_id])
                )

    return all_team_members


def list_team_sources(team: Team) -> list[Source]:
    """
    List all sources for a given team
    """

    wrapper = lambda parameters: CONFIG.client.list_team_sources(
        team.id, parameters=parameters
    )
    return pagination_max_results(wrapper)


def list_all_teams() -> tuple[list[Team], dict[str, Team]]:
    """
    Get syncable teams from GitGuardian and teams by external id
    """

    all_teams: list[Team] = pagination_max_results(
        CONFIG.client.list_teams, TeamsParameters, {"is_global": False}
    )

    sync_teams = []
    teams_by_external_id: dict[str, Team] = {}
    for team in all_teams:
        if external_id := team_gitlab_id(team):
            teams_by_external_id[external_id] = team
            sync_teams.append(team)

    return sync_teams, teams_by_external_id


def list_all_members() -> list[Member]:
    """
    Get all members from GitGuardian
    """

    return pagination_max_results(CONFIG.client.list_members)


def list_all_invitations() -> list[Invitation]:
    """
    Get all invitations from GitGuardian
    """

    return pagination_max_results(CONFIG.client.list_invitations)


def list_all_sources() -> list[Source]:
    """
    Get all sources from GitGuardian
    """

    return pagination_max_results(
        CONFIG.client.list_sources, SourceParameters, {"type": "gitlab"}
    )


def remove_team_member(team: Team, team_member_id: int):
    """
    Remove a member from a given team
    """

    response = CONFIG.client.delete_team_member(
        team_id=team.id, team_member_id=team_member_id
    )
    if isinstance(response, Detail):
        raise RuntimeError(f"Unable to remove team member: {response.detail}")

    logger.warning(
        f"Successfully removed member {team_member_id} from {team.name}",
    )


def remove_team_invitation(team: Team, invitation_id: int, email: str):
    response = CONFIG.client.delete_team_invitation(
        team_id=team.id, invitation_id=invitation_id
    )
    if isinstance(response, Detail):
        raise RuntimeError(f"Unable to remove team invitation: {response.detail}")

    logger.warning(
        f"Successfully removed team invitation for {email} from {team.name}",
    )


def send_invitation(
    member_email: str, access_level: AccessLevel = AccessLevel.MEMBER
) -> Invitation | None:
    """
    Send an invitation to join a workspace, the invitation is sent to member_email
    """

    domain = member_email.rsplit("@", 1)[-1]
    if CONFIG.invite_domains and domain not in CONFIG.invite_domains:
        logger.info("Email doesn't match invite domains: %s", member_email)
        return None

    payload = CreateInvitation(member_email, access_level)
    parameters = CreateInvitationParameters(send_email=CONFIG.send_email)
    response = CONFIG.client.create_invitation(
        invitation=payload, parameters=parameters
    )

    if isinstance(response, Detail):
        if response.status_code == 409:
            logger.debug(f"User {member_email} is already invited to the workspace")
        else:
            raise RuntimeError(f"Unable to invite member: {response.detail}")

    logger.info(f"Successfully invited member {member_email}")

    return response


def send_team_invitation(
    invitation: Invitation,
    team: Team,
    is_team_leader: bool = False,
    incident_permission: IncidentPermission = CONFIG.default_incident_permission,
) -> TeamInvitation | None:
    """
    From an invitation, invite the member to the team
    """
    payload = CreateTeamInvitation(invitation.id, is_team_leader, incident_permission)
    response = CONFIG.client.create_team_invitation(team_id=team.id, invitation=payload)

    if isinstance(response, Detail):
        if response.status_code == 409:
            logger.debug(
                f"User {invitation.email} is already invited to the team ({team.name})"
            )
            return None
        raise RuntimeError(f"Unable to invite member to the team: {response.detail}")

    logger.info(
        f"Successfully invited member {invitation.email} to the team {team.name}",
    )

    return response


def add_member_to_team(
    member: Member,
    team: Team,
    is_team_leader: bool = False,
    incident_permission: IncidentPermission = CONFIG.default_incident_permission,
):
    """
    Add a member to the team
    """

    if member.access_level in (AccessLevel.OWNER, AccessLevel.MANAGER):
        is_team_leader = True
        incident_permission = IncidentPermission.FULL_ACCESS

    payload = CreateTeamMember(
        member_id=member.id,
        is_team_leader=is_team_leader,
        incident_permission=incident_permission,
    )
    parameters = CreateTeamMemberParameters(send_email=CONFIG.send_email)
    response = CONFIG.client.create_team_member(
        team_id=team.id, member=payload, parameters=parameters
    )

    if isinstance(response, Detail):
        if response.status_code == 409:
            logger.debug(
                f"User {member.email} is already a member of the team ({team.name})"
            )
            return
        raise RuntimeError(f"Unable to add member to the team: {response.detail}")

    logger.info(
        f"Successfully added member to the team {member.email}",
    )


def list_sources_by_team_id(all_teams: Iterable[Team]) -> dict[int, list[Source]]:
    """
    Give a list of teams, return all their sources mapped by team id to a list of source
    """
    source_by_team_id = defaultdict(list)
    for team in all_teams:
        team_sources = list_team_sources(team)
        source_by_team_id[team.id] = team_sources

    return source_by_team_id


def delete_team(team: Team):
    response = CONFIG.client.delete_team(team.id)

    if isinstance(response, Detail):
        raise RuntimeError(f"Unable to delete team {team.name}: {response.detail}")

    logger.info(f"Successfully deleted team {team.name}")


def delete_teams_by_name(
    all_teams: list[Team],
    team_names_to_delete: set[str],
    sources_by_team_id: dict[int, list[Source]],
):
    """
    Given every team available in GitGuardian, remove teams that are in the set of
    team to delete
    It will not delete teams that have sources outside of gitlab
    """

    to_remove = [team for team in all_teams if team.name in team_names_to_delete]

    for team in to_remove:
        team_sources = sources_by_team_id[team.id]
        if any(source.type != "gitlab" for source in team_sources):
            logger.warning(
                f"Cannot delete team {team.name}, it has sources not in gitlab"
            )
        else:
            CONFIG.client.delete_team(team.id)
            logger.warning(
                f"Successfully deleted team {team.name}",
            )


def create_new_teams(teams: set[str]) -> list[Team]:
    """
    Create all teams defined in the set
    """

    new_teams = []
    for team in teams:
        team = CONFIG.client.create_team(CreateTeam(name=team))
        new_teams.append(team)

        logger.info(
            f"Successfully created team {team.name}",
        )

    return new_teams


def update_team_source(
    team: Team, sources_to_add: list[int], sources_to_remove: list[int]
):
    """
    Updates the sources for a team
    """

    payload = UpdateTeamSource(team.id, sources_to_add, sources_to_remove)
    response = CONFIG.client.update_team_source(payload)

    if isinstance(response, Detail):
        raise RuntimeError(f"Unable to update team source: {response.detail}")

    logger.info(
        f"Successfully updated sources for team {team.name}",
    )


def delete_invitation(invitation: Invitation):
    response = CONFIG.client.delete_invitation(invitation.id)

    if isinstance(response, Detail):
        raise RuntimeError(f"Unable to delete invitation: {response.detail}")

    logger.info(
        f"Successfully deleted invitation for {invitation.email}",
    )


def delete_invitations(invitations: Iterable[Invitation]):
    for invitation in invitations:
        delete_invitation(invitation)


def delete_member(member: Member):
    """
    Delete a member from the workspace
    """

    if not CONFIG.remove_members:
        logger.debug("Removing members is disabled, skipping...")
        return

    payload = DeleteMemberParameters(member.id, send_email=CONFIG.send_email)
    response = CONFIG.client.delete_member(payload)

    if isinstance(response, Detail):
        logger.error(f"Unable to delete member : {member.email}")
    else:
        logger.info(f"Successfully deleted member {member.email}")


def deactivate_member(member: Member):
    """
    Deactivate a member from the workspace
    """

    response = CONFIG.client.update_member(
        UpdateMember(member.id, active=False, access_level=AccessLevel.RESTRICTED)
    )

    if isinstance(response, Detail):
        logger.error(f"Unable to deactivate member : {member.email}")
    else:
        logger.info(f"Successfully deactivated member {member.email}")


def remove_members(members_to_delete: Iterable[Member]):
    """
    Delete or deactive members from the workspace depending on CONFIG
    """

    if not CONFIG.remove_members:
        logger.debug("Removing members is disabled, skipping...")
        return

    for member in members_to_delete:
        delete_member(member)


def list_team_invitations(team: Team) -> list[TeamInvitation]:
    wrapper = lambda parameters: CONFIG.client.list_team_invitations(
        team.id, parameters=parameters
    )
    return pagination_max_results(wrapper)
