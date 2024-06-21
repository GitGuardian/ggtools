from dataclasses import dataclass

import requests
from client import VCSClient, VCSRepoClient
from common import (
    CredentialsValidationError,
    PullRequestCreationError,
    PullRequestInfo,
    RepositoryAccessError,
    RepositoryInfo,
)


@dataclass
class BitBucketRepositoryInfo(RepositoryInfo):
    project: str


class BitBucketClient(VCSClient):
    @property
    def common_url_path(self) -> str | None:
        return "rest/api/1.0"

    def validate_credentials(self):
        try:
            resp = self.get("users")
            resp.json()
            if not resp.ok:
                raise CredentialsValidationError(
                    f"Invalid BitBucket token for {self.instance_url}"
                )
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.JSONDecodeError,
        ):
            raise CredentialsValidationError(
                f"Can't connect to BitBucket at {self.instance_url}"
            )

    def get_repository_info(self, repo_name: str) -> RepositoryInfo:
        repo_paths = repo_name.split("/")

        if len(repo_paths) != 2:
            raise RepositoryAccessError(
                "Project name should be included in the repository path: project/repository"
            )

        project_key, repository_slug = repo_paths

        resp = self.get(f"projects/{project_key}/repos/{repository_slug}")
        if not resp.ok:
            raise RepositoryAccessError(
                f"Can't get repository info for {repo_name}: {resp.json()['errors'][0]['message']}"
            )

        data = resp.json()
        repo_id = data["id"]

        resp = self.get(
            f"projects/{project_key}/repos/{repository_slug}/default-branch"
        )
        if not resp.ok:
            raise RepositoryAccessError(
                f"Can't get default branch for {repo_name}: {resp.json()['errors'][0]['message']}"
            )

        data = resp.json()
        default_branch = data["id"]

        return BitBucketRepositoryInfo(
            main_language=None,
            default_branch=default_branch,
            name=repository_slug,
            id=repo_id,
            project=project_key,
        )


class BitBucketRepoClient(VCSRepoClient):
    @property
    def common_url_path(self) -> str | None:
        return f"rest/api/1.0/projects/{self.repo_info.project}/repos/{self.repo_info.name}"

    def create_new_branch(self, branch_name: str, target_branch_name: str):
        resp = self.post(
            "branches",
            json={"name": branch_name, "startPoint": target_branch_name},
        )
        if not resp.ok:
            raise PullRequestCreationError(
                f"Can't create new branch: {resp.json()['errors'][0]['message']}"
            )

    def create_new_commit(
        self, pr_info: PullRequestInfo, repo_info: RepositoryInfo
    ) -> None:
        resp = self.put(
            f"browse/{pr_info.filename}",
            data={
                "content": pr_info.content,
                "message": pr_info.commit_message,
                "branch": pr_info.branch,
            },
        )

        if not resp.ok:
            raise PullRequestCreationError(
                f"Can't create new commit: {resp.json()['errors'][0]['message']}"
            )

    def create_pull_request(
        self,
        branch_name: str,
        target_branch_name: str,
        title: str,
    ) -> str:
        project = self.repo_info.project
        repo = self.repo_info.name

        payload = {
            "title": title,
            "description": "",
            "state": "OPEN",
            "open": True,
            "closed": False,
            "fromRef": {
                "id": f"refs/heads/{branch_name}",
                "repository": {
                    "slug": repo,
                    "project": {"key": project},
                },
            },
            "toRef": {
                "id": target_branch_name,
                "repository": {
                    "slug": repo,
                    "project": {"key": project},
                },
            },
            "locked": False,
        }
        resp = self.post("pull-requests", json=payload)

        if not resp.ok:
            raise PullRequestCreationError(
                f"Failed to create pull request: {resp.json()['errors'][0]['message']}"
            )

        data = resp.json()

        return data["links"]["self"][0]["href"]

    def delete_branch(self, branch_name: str) -> None:
        # use here directly requests since different api is used to delete branch
        resp = requests.delete(
            f"{self.instance_url}/rest/branch-utils/1.0/projects/{self.repo_info.project}/"
            f"repos/{self.repo_info.name}/"
            "branches",
            headers=self.headers,
            json={"name": branch_name},
        )

        if not resp.ok:
            raise PullRequestCreationError(
                f"Can't delete branch: {resp.json()['errors'][0]['message']}"
            )
