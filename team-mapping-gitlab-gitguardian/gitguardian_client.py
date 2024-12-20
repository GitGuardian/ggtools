import logging

from urllib.parse import urlparse, parse_qs
from pygitguardian.models import (
    AccessLevel,
    CreateInvitation,
    CreateInvitationParameters,
    CreateTeam,
    CreateTeamInvitation,
    CreateTeamMember,
    CreateTeamMemberParameters,
    Detail,
    IncidentPermission,
    Invitation,
    Member,
    Source,
    SourceParameters,
    Team,
    TeamInvitation,
    TeamsParameters,
    UpdateTeamSource,
)
from pygitguardian.models_utils import (
    CursorPaginatedResponse,
    PaginationParameter,
)
from typing import Any

from config import CONFIG

logger = logging.getLogger(__name__)


def get_cursor(url: str) -> str | None:
    """
    Extract cursor query parameter from a URL
    """
    parsed_url = urlparse(url)

    query_params = parse_qs(parsed_url.query)
    return query_params.get("cursor", [None])[0]


def pagination_max_results(
    method: Any, parameter_cls=PaginationParameter, additional_parameters=dict()
) -> list:
    """
    Iterate over all pages of a paginated response from GitGuardian API

    Use Parameters inheritance from PaginationParameter to loop
    on all `list` methods
    """

    pagination_parameters = parameter_cls(**additional_parameters)
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
        pagination_parameters = parameter_cls(cursor=cursor, **additional_parameters)
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
    all_team_members = dict()
    for team in all_teams:
        all_team_members[team.name] = []
        list_team_members = lambda parameters: CONFIG.client.list_team_members(
            team.id, parameters=parameters
        )
        team_members = pagination_max_results(list_team_members)
        for team_member in team_members:
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


def list_all_teams() -> list[Team]:
    """
    Get all teams from GitGuardian
    """

    return pagination_max_results(
        CONFIG.client.list_teams, TeamsParameters, {"is_global": False}
    )


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
        raise RuntimeError(f"Unable to remove team member: {response.content}")

    logger.warning(
        "Successfully removed team member",
        extra=dict(
            team_id=team.id,
            team_name=team.name,
            team_member_id=team_member_id,
        ),
    )


def send_invitation(
    member_email: str, access_level: AccessLevel = AccessLevel.MEMBER
) -> Invitation:
    """
    Send an invitation to join a workspace, the invitation is sent to member_email
    """

    payload = CreateInvitation(member_email, access_level)
    parameters = CreateInvitationParameters(send_email=CONFIG.send_email)
    response = CONFIG.client.create_invitation(
        invitation=payload, parameters=parameters
    )

    if isinstance(response, Detail):
        raise RuntimeError(f"Unable to invite member: {response.content}")

    logger.info("Successfully invited member", email=member_email)

    return response


def send_team_invitation(
    invitation: Invitation,
    team: Team,
    is_team_leader: bool = False,
    incident_permission: IncidentPermission = CONFIG.default_incident_permission,
) -> TeamInvitation:
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
            return
        raise RuntimeError(f"Unable to invite member to the team: {response.content}")

    logger.info(
        "Successfully invited member to the team",
        extra=dict(
            email=invitation.email,
            team_id=team.id,
            team_name=team.name,
        ),
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
        else:

            raise RuntimeError(f"Unable to add member to the team: {response.content}")

    logger.info(
        "Successfully added member to the team",
        extra=dict(
            email=member.email,
            team_id=team.id,
            team_name=team.name,
        ),
    )


def delete_teams_by_name(all_teams: list[Team], team_names_to_delete: set[str]):
    """
    Given every team available in GitGuardian, remove teams that are in the set of
    team to delete
    """

    to_remove = [team for team in all_teams if team.name in team_names_to_delete]

    for team in to_remove:
        CONFIG.client.delete_team(team.id)
        logger.warning(
            "Successfully deleted team",
            extra=dict(team_id=team.id, team_name=team.name),
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
            "Successfully created team",
            extra=dict(team_id=team.id, team_name=team.name),
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
        raise RuntimeError(f"Unable to update team source: {response.content}")

    logger.info(
        "Successfully updated team sources",
        extra=dict(
            team_id=team.id,
            team_name=team.name,
            sources_added=sources_to_add,
            sources_removed=sources_to_remove,
        ),
    )
