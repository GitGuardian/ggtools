import requests
from client import VCSClient, VCSRepoClient
from common import (
    GITHUB_SAAS,
    CredentialsValidationError,
    PullRequestCreationError,
    PullRequestInfo,
    RepositoryAccessError,
    RepositoryInfo,
)


class GitHubClient(VCSClient):
    @property
    def common_url_path(self) -> str | None:
        if self.instance_url != GITHUB_SAAS:
            return "api/v3"
        return None

    def validate_credentials(self) -> None:
        try:
            resp = self.get("user")
            resp.json()
            if not resp.ok:
                raise CredentialsValidationError(
                    f"Invalid GitHub token for {self.instance_url}"
                )
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.JSONDecodeError,
        ):
            raise CredentialsValidationError(
                f"Can't connect to GitHub at {self.instance_url}"
            )

    def get_repository_info(self, repo_name: str) -> RepositoryInfo:
        """
        Get the info about the GitHub repository
        """
        resp = self.get(f"repos/{repo_name}")

        if not resp.ok:
            raise RepositoryAccessError(
                f"Can't get repository info for {repo_name}: {resp.json()['message']}"
            )

        data = resp.json()
        language = data.get("language", None)
        if language:
            language = language.lower()

        default_branch = data.get("default_branch", None)
        if not default_branch:
            raise RepositoryAccessError(
                f"Repository does not have a default branch: {repo_name}"
            )

        return RepositoryInfo(
            main_language=language,
            default_branch=default_branch,
            name=repo_name,
            id=data["id"],
        )


class GitHubRepoClient(VCSRepoClient):
    @property
    def common_url_path(self) -> str | None:
        if self.instance_url != GITHUB_SAAS:
            return f"api/v3/repos/{self.repo_info.name}"
        return f"repos/{self.repo_info.name}"

    def create_new_branch(
        self,
        branch_name: str,
        target_branch: str,
    ) -> None:
        """
        Create a new branch on a repository from the target branch.
        """
        resp = self.get(f"branches/{target_branch}")

        if not resp.ok:
            raise PullRequestCreationError(f"Can't find branch: {target_branch}")

        data = resp.json()
        last_commit_sha = data["commit"]["sha"]

        resp = self.post(
            "git/refs",
            json={
                "ref": f"refs/heads/{branch_name}",
                "sha": last_commit_sha,
            },
        )
        if not resp.ok:
            raise PullRequestCreationError(
                f"Can't create new branch: {resp.json()['message']}"
            )

    def _create_new_tree(
        self,
        tree_sha_to_update: str,
        tree_update: list[dict],
    ) -> str:
        """
        Create a new tree object and return the new tree hash
        """
        resp = self.post(
            "git/trees",
            json={
                "base_tree": tree_sha_to_update,
                "tree": tree_update,
            },
        )
        if not resp.ok:
            raise PullRequestCreationError(
                "Error in git tree modification.\n "
                "It can happen if your trying to do an impossible action like create an "
                f"existing file or delete/move a non-existing file: {resp.json()['message']}"
            )

        return resp.json()["sha"]

    def _add_commit_to_branch(
        self,
        branch_name: str,
        commit_sha: str,
    ) -> None:
        """
        Add commit to a branch
        """
        resp = self.post(
            f"git/refs/heads/{branch_name}",
            json={"sha": commit_sha},
        )
        if not resp.ok:
            raise PullRequestCreationError(
                f"Could not add commit: {resp.json()['message']}"
            )

    def _create_new_commit(
        self,
        commit_msg: str,
        tree_sha: str,
        parent_commit_sha: str,
    ) -> str:
        """
        Creation a new commit from a parent commit and a tree hash
        """
        json_payload = {
            "message": commit_msg,
            "tree": tree_sha,
            "parents": [parent_commit_sha],
        }

        resp = self.post(
            "git/commits",
            json=json_payload,
        )
        if not resp.ok:
            raise PullRequestCreationError(
                f"Error in git commit creation: {resp.json()['message']}"
            )
        return resp.json()["sha"]

    def create_new_commit(
        self, pr_info: PullRequestInfo, repo_info: RepositoryInfo
    ) -> None:
        resp = self.get(f"branches/{repo_info.default_branch}")

        if not resp.ok:
            raise PullRequestCreationError(
                f"Can't find branch: {repo_info.default_branch}"
            )

        data = resp.json()
        last_commit_sha = data["commit"]["sha"]
        last_tree_sha = data["commit"]["commit"]["tree"]["sha"]

        new_tree_sha = self._create_new_tree(
            tree_sha_to_update=last_tree_sha,
            tree_update=[
                {
                    "path": pr_info.filename,
                    "mode": "100644",
                    "type": "blob",
                    "content": pr_info.content,
                }
            ],
        )

        new_commit_sha = self._create_new_commit(
            pr_info.commit_message, new_tree_sha, last_commit_sha
        )

        self._add_commit_to_branch(
            branch_name=pr_info.branch,
            commit_sha=new_commit_sha,
        )

    def delete_branch(
        self,
        branch_name: str,
    ):
        """
        Delete a branch on a GitHub repository
        """
        self.delete(f"git/refs/heads/{branch_name}")

    def create_pull_request(
        self, branch_name: str, target_branch: str, title: str
    ) -> str:
        pr_response = self.post(
            "pulls",
            json={
                "repo": self.repo_info.name,
                "title": title,
                "body": "",
                "head": branch_name,
                "base": target_branch,
            },
        )

        if not pr_response.ok:
            raise PullRequestCreationError(
                f"Error in creating pull request: {pr_response.json()['message']}"
            )

        return pr_response.json()["html_url"]
