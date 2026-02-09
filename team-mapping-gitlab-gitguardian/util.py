import json
import logging
from typing import Iterable, TypedDict

from email_validator import EmailNotValidError, validate_email
from pygitguardian.models import Team

from config import CONFIG

logger = logging.getLogger(__name__)

GitlabUserGroup = TypedDict(
    "GitlabUserGroup",
    {
        "name": str,
        "email": str | None,
        "groupMemberships": list[dict[str, str]],
    },
)
GitlabUser = TypedDict(
    "GitlabUser",
    {
        "name": str,
        "email": str | None,
    },
)
GitlabGroup = TypedDict(
    "GitlabGroup",
    {
        "id": str,
        "fullName": str,
        "fullPath": str,
        "users": list[GitlabUser],
    },
)
GitlabProject = TypedDict(
    "GitlabProject",
    {
        "id": str,
        "name": str,
        "fullPath": str,
        "group": str | None,
    },
)


def team_description_from_group(group: GitlabGroup) -> str:
    keys_to_keep = {"id", "fullPath"}
    return json.dumps(
        {key: value for key, value in group.items() if key in keys_to_keep}
    )


def team_gitlab_id(team: Team) -> str | None:
    if team.description:
        try:
            metadata = json.loads(team.description)
            if "id" in metadata:
                return metadata["id"]
        except json.JSONDecodeError:
            pass
    return None


def transform_gitlab_user(gitlab_user: dict) -> GitlabUserGroup:
    """
    Transform the GraphQL representation of a User to a simpler dictionary
    """

    groups = []
    memberships = gitlab_user.get("groupMemberships", {}).get("nodes", [])

    for membership in memberships:
        if membership["accessLevel"]["integerValue"] >= CONFIG.gitlab_level:
            group = membership["group"]
            group["fullPath"] = " / ".join(group["fullPath"].split("/"))
            groups.append(group)

    return {
        "name": gitlab_user["name"],
        "email": get_valid_email(e["email"] for e in gitlab_user["emails"]["nodes"]),
        "groupMemberships": groups,
    }


def transform_gitlab_project(gitlab_project: dict) -> GitlabProject:
    group = gitlab_project["group"] or {"id": None}
    full_path = " / ".join(gitlab_project["fullPath"].split("/"))
    return {
        "id": gitlab_project["id"].split("/")[-1],
        "name": gitlab_project["name"],
        "fullPath": full_path,
        "group": group["id"],
    }


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
