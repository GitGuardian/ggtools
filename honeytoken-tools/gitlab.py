import urllib.parse

import requests
from client import VCSClient, VCSRepoClient
from common import (
    CredentialsValidationError,
    PullRequestCreationError,
    PullRequestInfo,
    RepositoryAccessError,
    RepositoryInfo,
)


class GitLabClient(VCSClient):
    @property
    def common_url_path(self) -> str | None:
        return "api/v4"

    def validate_credentials(self) -> None:
        try:
            resp = self.get("version")
            resp.json()
            if resp.status_code == 401:
                raise CredentialsValidationError(
                    f"Invalid Gitlab token for {self.instance_url}"
                )
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.JSONDecodeError,
        ):
            raise CredentialsValidationError(
                f"Can't connect to Gitlab at {self.instance_url}"
            )

    def get_repository_info(self, repo_name: str) -> RepositoryInfo:
        """
        Get the info about the Gitlab project
        """
        repo_name_safe = urllib.parse.quote_plus(repo_name)
        resp = self.get(f"projects/{repo_name_safe}")

        if not resp.ok:
            raise RepositoryAccessError(
                f"Can't get repository info for {repo_name}: {resp.json()['message']}"
            )

        data = resp.json()
        default_branch = data.get("default_branch", None)
        name = data["name_with_namespace"]
        repo_id = data["id"]

        if not default_branch:
            raise RepositoryAccessError(
                f"Repository does not have a default branch: {repo_name}"
            )

        resp = self.get(f"projects/{repo_id}/languages")
        data = resp.json()

        language = None
        if data:
            language = list(data.keys())[0].lower()

        return RepositoryInfo(
            main_language=language,
            default_branch=default_branch,
            name=name,
            id=repo_id,
        )


class GitLabRepoClient(VCSRepoClient):
    @property
    def common_url_path(self) -> str | None:
        return f"api/v4/projects/{self.repo_info.id}"

    def create_new_branch(
        self,
        branch_name: str,
        target_branch: str,
    ) -> None:
        """
        Create a new branch on a GitLab project with the name branch_name from the target_branch
        """
        resp = self.post(
            "repository/branches",
            json={
                "ref": target_branch,
                "branch": branch_name,
            },
        )
        if not resp.ok:
            raise PullRequestCreationError(
                f"Can't create new branch: {resp.json()['message']}"
            )

    def create_new_commit(
        self, pr_info: PullRequestInfo, repo_info: RepositoryInfo
    ) -> None:
        json_payload = {
            "branch": pr_info.branch,
            "commit_message": pr_info.commit_message,
            "actions": [
                {
                    "action": "create",
                    "file_path": pr_info.filename,
                    "content": pr_info.content,
                }
            ],
        }

        resp = self.post(
            "repository/commits",
            json=json_payload,
        )
        if not resp.ok:
            raise PullRequestCreationError(
                f"Error in git commit creation: {resp.json()['message']}"
            )

    def create_pull_request(
        self, branch_name: str, target_branch: str, title: str
    ) -> str:
        resp = self.post(
            "merge_requests",
            json={
                "source_branch": branch_name,
                "target_branch": target_branch,
                "title": title,
                "description": "",
            },
        )
        if not resp.ok:
            raise PullRequestCreationError(
                f"Failed to create pull request: {resp.json()['message']}"
            )

        data = resp.json()

        return data["web_url"]

    def delete_branch(self, branch_name: str) -> None:
        self.delete(
            f"repository/branches/{branch_name}",
        )
