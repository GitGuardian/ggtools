import requests

from config import CONFIG
from util import (
    GitlabProject,
    GitlabUserGroup,
    transform_gitlab_project,
    transform_gitlab_user,
)

GITLAB_USER_GRAPHQL_QUERY = """
query ($cursor: String) {
  users(first: 100, after: $cursor, humans: true) {
    pageInfo {
      endCursor
      hasNextPage
    }
    nodes {
      name
      emails {
        nodes {
          email
        }
      }
      groupMemberships {
        nodes {
          accessLevel {
            integerValue
          }
          group {
            id
            name
            fullName
            fullPath
          }
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
                id
                name
                fullName
                fullPath
            }
        }
    }
}
"""


def fetch_gitlab_users() -> list[GitlabUserGroup]:
    """
    Fetch all Gitlab users and their groups using GraphQL, iterate on pagination if needed
    """

    users = []

    url = f"{CONFIG.gitlab_url}/api/graphql"
    headers = {"Authorization": f"Bearer {CONFIG.gitlab_token}"}

    default_variables: dict[str, str] = {}
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
            timeout=60,
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

    default_variables: dict[str, str] = {}
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
