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
class ADORepositoryInfo(RepositoryInfo):
    organization: str
    project: str


class ADOClient(VCSClient):
    token_prefix = "Basic"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.headers["Accept"] = "application/json;api-version=6.0;"

    def validate_credentials(self) -> None:
        """
        There is no api that can be used to validate the credentials without organization.
        The credentials will be validated in the get_repository_info method when trying to access each of the repositories
        """
        pass

    def get_repository_info(self, repo_name: str) -> RepositoryInfo:
        repo_paths = repo_name.split("/")

        if len(repo_paths) != 3:
            raise RepositoryAccessError(
                "Organization and project names should be included in the repository path: "
                "organization/project/repository"
            )

        organization, project, repository = repo_paths

        try:
            resp = self.get(
                f"{organization}/{project}/_apis/git/repositories/{repository}"
            )
            resp.json()
            if resp.status_code == 401:
                raise CredentialsValidationError(
                    f"Invalid Azure DevOps token for {self.instance_url}"
                )
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.JSONDecodeError,
        ):
            raise CredentialsValidationError(
                f"Can't connect to Azure DevOps at {self.instance_url}"
            )

        if not resp.ok:
            raise RepositoryAccessError(
                f"Can't get repository info for {repo_name}: {resp.json()['message']}"
            )

        data = resp.json()
        default_branch = data.get("defaultBranch", None)
        name = data["name"]
        repo_id = data["id"]

        if not default_branch:
            raise RepositoryAccessError(
                f"Repository does not have a default branch: {repo_name}"
            )

        language = None

        resp = self.get(
            f"{organization}/{project}/_apis/projectanalysis/languagemetrics"
        )

        if resp.status_code == 401:
            print(
                f"Can't get language metrics for {repo_name}. You need to include Analytics scope for your PAT"
            )
        else:
            data = resp.json()

            if data and "languageBreakdown" in data:
                language_data = data["languageBreakdown"]
                if language_data:
                    language = language_data[0]["name"].lower()

        return ADORepositoryInfo(
            main_language=language,
            default_branch=default_branch,
            name=name,
            id=repo_id,
            project=project,
            organization=organization,
        )


class ADORepoClient(VCSRepoClient):
    token_prefix = "Basic"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.headers["Accept"] = "application/json;api-version=6.0;"

    @property
    def common_url_path(self) -> str | None:
        return f"{self.repo_info.organization}/{self.repo_info.project}/_apis/git/repositories/{self.repo_info.id}"

    def create_new_branch(
        self,
        branch_name: str,
        target_branch: str,
    ) -> None:
        # Branch is created at the same time as the commit is created in create_new_commit
        pass

    def create_new_commit(
        self, pr_info: PullRequestInfo, repo_info: RepositoryInfo
    ) -> None:
        target_branch = repo_info.default_branch
        new_branch = pr_info.branch

        resp = self.get(target_branch)

        if not resp.ok:
            raise PullRequestCreationError(
                f"Failed to fetch the last commit on branch {target_branch}: {resp.json()['message']}"
            )

        latest_commit = resp.json()["value"][0]["objectId"]

        resp = self.post(
            "pushes",
            json={
                "refUpdates": [
                    {"name": f"refs/heads/{new_branch}", "oldObjectId": latest_commit}
                ],
                "commits": [
                    {
                        "comment": pr_info.commit_message,
                        "changes": [
                            {
                                "changeType": "add",
                                "item": {"path": f"/{pr_info.filename}"},
                                "newContent": {
                                    "content": pr_info.content,
                                    "contentType": "rawtext",
                                },
                            }
                        ],
                    }
                ],
            },
        )

        if not resp.ok:
            raise PullRequestCreationError(
                f"Can't create new branch: {resp.json()['message']}"
            )

    def create_pull_request(
        self, branch_name: str, target_branch: str, title: str
    ) -> str:
        resp = self.post(
            "pullRequests",
            json={
                "sourceRefName": f"refs/heads/{branch_name}",
                "targetRefName": target_branch,
                "title": title,
                "description": "",
                "reviewers": [],
            },
        )

        if not resp.ok:
            raise PullRequestCreationError(
                f"Failed to create pull request: {resp.json()['message']}"
            )

        data = resp.json()

        return f"{data['repository']['webUrl']}/pullrequest/{data['pullRequestId']}"

    def delete_branch(self, branch_name: str) -> None:
        """
        Delete a branch
        """
        resp = self.get(f"refs?filter=heads/{branch_name}")
        refs = resp.json()["value"]

        if not refs:
            raise PullRequestCreationError(f"Failed to clean up {branch_name}.")

        ref = refs[0]

        self.post(
            "refs",
            json=[
                {
                    "name": ref["name"],
                    "oldObjectId": ref["objectId"],
                    "newObjectId": "0000000000000000000000000000000000000000",
                }
            ],
        )
