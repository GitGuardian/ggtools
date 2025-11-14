import logging
import re
from urllib.parse import parse_qs, urlparse
from pygitguardian.models import (
    CreateInvitation,
    CreateInvitationParameters,
    AccessLevel,
    Invitation,
    CreateTeamInvitation,
    Member,
    Team,
    TeamInvitation,
    TeamMember,
    Detail,
    CreateTeamMember,
    CreateTeamMemberParameters,
    CreateTeam,
    UpdateTeam,
    IncidentPermission,
    UpdateTeamSource,
    Source,
    SourceParameters,
    TeamSourceParameters,
    TeamMemberParameters,
    TeamInvitationParameters,
    InvitationParameters,
    TeamsParameters,
    MembersParameters
)
from collections.abc import Generator
from typing import Optional
from config import CONFIG


logger = logging.getLogger(__name__)


def list_all_gg_invitations() -> Generator[Invitation]:
    """Fetch all installations existing on the workspace by iterating over the pagination."""
    first_call = True
    cursor = ''

    while first_call or cursor:
        first_call = False

        parameters = InvitationParameters(cursor=cursor, per_page=100)
        response = CONFIG.gg_client.list_invitations(parameters)

        if isinstance(response, Detail):
            raise RuntimeError(f"Error while listing members: {response.detail}")

        cursor = _extract_cursor(response.next) if response.next else ''
        yield from response.data


def list_all_gg_members() -> Generator[Member]:
    """Fetch all members existing on the workspace by iterating over the pagination."""
    first_call = True
    cursor = ''
    iteration = 0
    max_iterations = 1000  # Safety limit to prevent infinite loops
    previous_next_url = None

    while first_call or cursor:
        iteration += 1
        if iteration > max_iterations:
            raise RuntimeError(f"Infinite loop detected: exceeded {max_iterations} iterations. Last cursor: {cursor}")
        
        first_call = False

        print(f"\n[DEBUG] Iteration #{iteration}")
        print(f"[DEBUG] Current cursor: '{cursor}'")
        
        parameters = MembersParameters(cursor=cursor, per_page=100)
        response = CONFIG.gg_client.list_members(parameters)

        if isinstance(response, Detail):
            raise RuntimeError(f"Error while listing members: {response.detail}")

        print(f"[DEBUG] Response type: {type(response)}")
        print(f"[DEBUG] Response.next value: {response.next}")
        print(f"[DEBUG] Response.next type: {type(response.next)}")
        data_length = len(response.data) if hasattr(response, 'data') else 0
        print(f"[DEBUG] Response.data length: {data_length}")
        
        # Check if we've reached the end (no more data)
        if not hasattr(response, 'data') or data_length == 0:
            print(f"[DEBUG] No more data returned, ending pagination")
            break
        
        # Extract cursor from response.next before checking
        old_cursor = cursor
        new_cursor = ''
        if response.next:
            print(f"[DEBUG] response.next is truthy, extracting cursor...")
            new_cursor = _extract_cursor(response.next)
        else:
            print(f"[DEBUG] response.next is falsy/None, no more pages")
        
        print(f"[DEBUG] Old cursor: '{old_cursor}'")
        print(f"[DEBUG] New cursor: '{new_cursor}'")
        print(f"[DEBUG] Cursor changed: {old_cursor != new_cursor}")
        
        # Yield the data first (before breaking)
        yield from response.data
        
        # Check multiple conditions to detect end of pagination:
        # 1. No next URL means we're done
        if not response.next:
            print(f"[DEBUG] No next URL, pagination complete")
            break
        
        # 2. If cursor didn't change and it's not empty, we've reached the end
        # (API is returning same cursor, indicating no more pages)
        if new_cursor == old_cursor and new_cursor != '' and iteration > 1:
            print(f"[INFO] Cursor did not change (same as previous: '{new_cursor}').")
            print(f"[INFO] This indicates we've reached the end of pagination.")
            print(f"[INFO] Breaking loop - pagination complete.")
            break
        
        # 3. If response.next URL is the same as previous, we're stuck/at end
        if response.next == previous_next_url and previous_next_url is not None:
            print(f"[INFO] response.next URL did not change (same as previous).")
            print(f"[INFO] This indicates we've reached the end of pagination.")
            print(f"[INFO] Breaking loop - pagination complete.")
            break
        
        # 4. If we got fewer items than requested, likely the last page
        if data_length < 100:  # per_page is 100
            print(f"[DEBUG] Received {data_length} items (less than per_page=100), likely last page")
            # Still continue if there's a next URL, but log it
        
        # Update for next iteration
        cursor = new_cursor
        previous_next_url = response.next


def list_all_gg_teams() -> Generator[Team]:
    """Fetch all teams existing on the workspace by iterating over the pagination."""
    first_call = True
    cursor = ''

    while first_call or cursor:
        first_call = False

        parameters = TeamsParameters(cursor=cursor, per_page=100)
        response = CONFIG.gg_client.list_teams(parameters)

        if isinstance(response, Detail):
            raise RuntimeError(f"Error while listing teams: {response.detail}")

        cursor = _extract_cursor(response.next) if response.next else ''
        yield from response.data


def list_all_gg_sources() -> Generator[Source]:
    """Fetch all GitHub sources existing on the workspace by iterating over the pagination."""
    first_call = True
    cursor = ''

    while first_call or cursor:
        first_call = False

        parameters = SourceParameters(type="github", cursor=cursor, per_page=100)
        response = CONFIG.gg_client.list_sources(parameters)

        if isinstance(response, Detail):
            raise RuntimeError(f"Error while listing sources: {response.detail}")

        cursor = _extract_cursor(response.next) if response.next else ''
        yield from response.data


def list_team_sources(team: Team) -> Generator[Source]:
    """Fetch the GitHub sources a team has access to."""
    first_call = True
    cursor = ''

    while first_call or cursor:
        first_call = False

        parameters = TeamSourceParameters(type="github", cursor=cursor, per_page=100)
        response = CONFIG.gg_client.list_team_sources(team_id=team.id, parameters=parameters)

        if isinstance(response, Detail):
            raise RuntimeError(f"Error while listing team sources: {response.detail}")

        cursor = _extract_cursor(response.next) if response.next else ''
        yield from response.data


def invite_user(email: str) -> Invitation:
    """Create a new invitation on the workspace for the given email."""
    parameters = CreateInvitationParameters(send_email=CONFIG.notify_users)
    create_invitation = CreateInvitation(email=email, access_level=AccessLevel.MEMBER)
    response = CONFIG.gg_client.create_invitation(create_invitation, parameters=parameters)

    if isinstance(response, Detail):
        raise RuntimeError(f"Error while inviting user {email}: {response.detail}")

    logger.info(f"Invited user {email}")
    return response


def create_team(name: str, description: Optional[str]) -> Team:
    """Create a new team on the workspace."""
    payload = CreateTeam(name=name, description=description)
    response = CONFIG.gg_client.create_team(payload)

    if isinstance(response, Detail):
        raise RuntimeError(f"Error while creating team {name}: {response.detail}")

    logger.info(f"Created team {name}")
    return response


def update_team(team_id: int, name: str) -> Team:
    """Update an existing team name on the workspace."""
    payload = UpdateTeam(id=team_id, name=name)
    response = CONFIG.gg_client.update_team(payload)

    if isinstance(response, Detail):
        raise RuntimeError(f"Error while updating team {name}: {response.detail}")

    logger.info(f"Updated team name {name}")
    return response


def delete_team(team: Team) -> None:
    """Remove a team from the workspace."""
    response = CONFIG.gg_client.delete_team(team.id)

    if isinstance(response, Detail):
        raise RuntimeError(f"Error while deleting team {team.name}: {response.detail}")

    logger.info(f"Deleted team {team.name}")
    return response


def list_team_members(team: Team) -> Generator[TeamMember]:
    first_call = True
    cursor = ''

    while first_call or cursor:
        first_call = False

        parameters = TeamMemberParameters(cursor=cursor, per_page=100)
        response = CONFIG.gg_client.list_team_members(team_id=team.id, parameters=parameters)

        if isinstance(response, Detail):
            raise RuntimeError(f"Error while listing team members: {response.detail}")

        cursor = _extract_cursor(response.next) if response.next else ''
        yield from response.data


def add_team_member(team: Team, member_id: int) -> None:
    payload = CreateTeamMember(
        member_id=member_id,
        is_team_leader=False,
        incident_permission=IncidentPermission.VIEW,
    )
    parameters = CreateTeamMemberParameters(send_email=CONFIG.notify_users)

    response = CONFIG.gg_client.create_team_member(
        team_id=team.id,
        member=payload,
        parameters=parameters,
    )

    if response.status_code == 409:
        logger.debug(f"User already belongs to team {team.name}")
        return

    if isinstance(response, Detail):
        logger.error(f"Error while adding user to team {team.name}: {response.detail}")

    logger.info(f"Added user to team {team.name}")


def delete_team_member(team: Team, team_member: TeamMember) -> None:
    response = CONFIG.gg_client.delete_team_member(team_id=team.id, team_member_id=team_member.id)

    if isinstance(response, Detail):
        logger.error(f"Error while removing user from team {team.name}: {response.detail}")

    logger.info(f"Removed user from team {team.name}")


def list_team_invitations(team: Team) -> Generator[TeamInvitation]:
    first_call = True
    cursor = ''

    while first_call or cursor:
        first_call = False

        parameters = TeamInvitationParameters(cursor=cursor, per_page=100)
        response = CONFIG.gg_client.list_team_invitations(team_id=team.id, parameters=parameters)

        if isinstance(response, Detail):
            raise RuntimeError(f"Error while listing team invitations: {response.detail}")

        cursor = _extract_cursor(response.next) if response.next else ''
        yield from response.data


def add_team_invitation(team: Team, invitation_id: int) -> None:
    payload = CreateTeamInvitation(
        invitation_id=invitation_id,
        is_team_leader=False,
        incident_permission=IncidentPermission.VIEW,
    )

    response = CONFIG.gg_client.create_team_invitation(
        team_id=team.id,
        invitation=payload,
    )

    if response.status_code == 409:
        logger.debug(f"User already invited to team {team.name}")
        return

    if isinstance(response, Detail):
        logger.error(f"Error while inviting user to team {team.name}: {response.detail}")

    logger.info(f"Invited user to team {team.name}")


def delete_team_invitation(team: Team, team_invitation: TeamInvitation) -> None:
    response = CONFIG.gg_client.delete_team_invitation(team_id=team.id, invitation_id=team_invitation.id)

    if isinstance(response, Detail):
        logger.error(f"Error while removing user from team {team.name}: {response.detail}")

    logger.info(f"Removed user from team {team.name}")


def update_team_sources(
    gg_team: Team,
    sources_to_add: list[int],
    sources_to_remove: list[int]
) -> None:
    payload = UpdateTeamSource(
        team_id=gg_team.id,
        sources_to_add=sources_to_add,
        sources_to_remove=sources_to_remove,
    )

    response = CONFIG.gg_client.update_team_source(payload)

    if isinstance(response, Detail):
        logger.error(f"Error while synchronizing team {gg_team.name} perimeter: {response.detail}")

    logger.info(f"Synchronized team {gg_team.name} perimeter")


def _extract_cursor(url: str) -> str:
    """Extract cursor from pagination URL."""
    print(f"[DEBUG _extract_cursor] Input URL: {url}")
    print(f"[DEBUG _extract_cursor] URL type: {type(url)}")
    
    parsed_url = urlparse(url)
    print(f"[DEBUG _extract_cursor] Parsed URL scheme: {parsed_url.scheme}")
    print(f"[DEBUG _extract_cursor] Parsed URL netloc: {parsed_url.netloc}")
    print(f"[DEBUG _extract_cursor] Parsed URL path: {parsed_url.path}")
    print(f"[DEBUG _extract_cursor] Parsed URL query: {parsed_url.query}")
    
    if parsed_url.query:
        parsed_query = parse_qs(parsed_url.query)
        print(f"[DEBUG _extract_cursor] Parsed query dict: {parsed_query}")
        print(f"[DEBUG _extract_cursor] Keys in parsed_query: {list(parsed_query.keys())}")
        
        if "cursor" in parsed_query and parsed_query["cursor"]:
            cursor_value = parsed_query["cursor"][0]
            print(f"[DEBUG _extract_cursor] Found cursor: '{cursor_value}'")
            return cursor_value
        else:
            print(f"[DEBUG _extract_cursor] No 'cursor' key found in query parameters")
    else:
        print(f"[DEBUG _extract_cursor] No query string in URL")
    
    print(f"[DEBUG _extract_cursor] Returning empty string")
    return ""
