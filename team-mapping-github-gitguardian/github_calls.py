from requests import request
from dataclasses import dataclass
from collections.abc import Generator
import logging
from config import CONFIG


class IdpNotImplementedException(Exception):
    ...


GH_SAML_USER_QUERY = """
query($after: String, $org:String!){
   organization(login: $org) {
        samlIdentityProvider {
            externalIdentities(first:100 , after:$after , membersOnly: true) {
                pageInfo {
                    endCursor startCursor hasNextPage
                }
                edges {
                    cursor node {
                        samlIdentity {
                            nameId
                            username
                        } user {
                            login
                        }
                    }
                }
            }
        }
    }
}
"""

GH_USER_QUERY = """
query($after: String, $org:String!){
   organization(login: $org) {
        membersWithRole(first:100 , after:$after) {
            pageInfo {
                endCursor startCursor hasNextPage
            }
            edges {
                cursor node {
                    email
                    login
                }
            }
        }
    }
}
"""

GH_USER_TEAM_QUERY = """
query($user:String!, $org:String!){
    organization(login: $org) {
        teams(first: 100, userLogins: [$user]) {
            totalCount
            pageInfo {
                endCursor startCursor hasNextPage
            }
            edges {
                node {
                    databaseId
                }
            }
        }
    }
}
"""


logger = logging.getLogger(__name__)


@dataclass
class GhUser:
    email: str
    username: str


def list_github_saml_users() -> Generator[GhUser]:
    """Loop over GitHub GraphQL pagination to retrieve the complete list of the organization SAML members."""
    after = None
    has_next_page = True

    while has_next_page:
        response = request(
            "post",
            f"{CONFIG.github_instance}/graphql",
            headers={
                "Authorization": f"token {CONFIG.github_token}",
                "Accept": "application/vnd.github.vixen-preview+json",
            },
            json={
                "query": GH_SAML_USER_QUERY,
                "variables": {"org": CONFIG.github_org, "after": after},
            },
        ).json()

        if response.get("errors"):
            raise RuntimeError("Error while fetching for github saml users")

        if response["data"]["organization"]["samlIdentityProvider"] is None:
            raise IdpNotImplementedException()

        has_next_page = response["data"]["organization"]["samlIdentityProvider"][
            "externalIdentities"]["pageInfo"]["hasNextPage"]
        after = response["data"]["organization"]["samlIdentityProvider"][
            "externalIdentities"]["pageInfo"]["endCursor"]

        page_data = response["data"]["organization"]["samlIdentityProvider"]["externalIdentities"]["edges"]
        yield from (
            GhUser(
                email=item["node"]["samlIdentity"]["nameId"],
                username=item["node"]["samlIdentity"]["username"],
            )
            for item in page_data
        )


def list_github_users() -> Generator[GhUser]:
    """Loop over GitHub GraphQL pagination to retrieve the complete list of the organization users."""
    after = None
    has_next_page = True

    while has_next_page:
        response = request(
            "post",
            f"{CONFIG.github_instance}/graphql",
            headers={
                "Authorization": f"token {CONFIG.github_token}",
                "Accept": "application/vnd.github.vixen-preview+json",
            },
            json={
                "query": GH_USER_QUERY,
                "variables": {"org": CONFIG.github_org, "after": after},
            },
        ).json()

        if response.get("errors"):
            raise RuntimeError("Error while fetching for github users")

        has_next_page = response["data"]["organization"]["membersWithRole"]["pageInfo"]["hasNextPage"]
        after = response["data"]["organization"]["membersWithRole"]["pageInfo"]["endCursor"]

        page_data = response["data"]["organization"]["membersWithRole"]["edges"]
        for item in page_data:
            if not item["node"]["email"]:
                logger.warning(f"User {item['node']['login']} does not have an email. Skip him.")
                continue
            elif not item["node"]["login"]:
                logger.warning(f"User={item['node']['email']} does not have a username. Skip him.")
                continue

            yield GhUser(
                email=item["node"]["email"],
                username=item["node"]["login"],
            )


def list_github_user_teams(user: GhUser) -> Generator[int]:
    """Loop over GitHub GraphQL pagination to retrieve the complete list of the user teams."""
    after = None
    has_next_page = True

    while has_next_page:
        response = request(
            "post",
            f"{CONFIG.github_instance}/graphql",
            headers={
                "Authorization": f"token {CONFIG.github_token}",
                "Accept": "application/vnd.github.vixen-preview+json",
            },
            json={
                "query": GH_USER_TEAM_QUERY,
                "variables": {"org": CONFIG.github_org, "user": user.username, "after": after},
            },
        ).json()

        if response.get("errors"):
            raise RuntimeError("Error while fetching for github teams")

        has_next_page = response['data']['organization']['teams']["pageInfo"]["hasNextPage"]
        after = response['data']['organization']['teams']["pageInfo"]["endCursor"]

        page_data = response['data']['organization']['teams']["edges"]
        yield from (
            item["node"]["databaseId"]
            for item in page_data
        )
