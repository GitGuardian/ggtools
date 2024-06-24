from copy import copy

import requests
from common import PullRequestInfo, RepositoryInfo


class ApiTokenClient:
    """
    Base class for API clients
    """

    token_prefix = "Bearer"
    common_url_path = None

    def __init__(
        self,
        instance_url: str,
        instance_token: str,
    ):
        self.instance_url = instance_url
        self.instance_token = instance_token

        self.headers = {
            "Authorization": f"{self.token_prefix} {self.instance_token}",
        }

    def get(self, path: str) -> requests.Response:
        return requests.get(self.get_url(path), headers=self.headers)

    def post(self, path: str, json) -> requests.Response:
        return requests.post(
            self.get_url(path),
            json=json,
            headers={**self.headers, "Content-Type": "application/json"},
        )

    def put(self, path: str, data: dict) -> requests.Response:
        return requests.put(
            self.get_url(path),
            files=data,
            headers=self.headers,
        )

    def delete(self, path: str) -> requests.Response:
        return requests.delete(self.get_url(path), headers=self.headers)

    def get_url(self, path: str) -> str:
        if self.common_url_path:
            return f"{self.instance_url}/{self.common_url_path}/{path}"
        else:
            return f"{self.instance_url}/{path}"


class VCSClient(ApiTokenClient):
    """
    Base class for VCS clients
    """

    def validate_credentials(self) -> None:
        """
        Validate the credentials and connection to the VCS with the credentials
        :return:
        """
        raise NotImplementedError

    def get_repository_info(self, repository_name: str) -> RepositoryInfo:
        """
        Get the info about the repository
        :param repository_name:
        :return: info about the repository
        """
        raise NotImplementedError


class VCSRepoClient(VCSClient):
    def __init__(self, repo_info: RepositoryInfo, *args, **kwargs):
        self.repo_info = repo_info
        super().__init__(*args, **kwargs)

    def create_new_branch(
        self,
        branch_name: str,
        target_branch: str,
    ) -> None:
        """
        Create a new branch on a repository from the target branch.
        """
        raise NotImplementedError

    def delete_branch(self, branch_name: str) -> None:
        """
        Delete a branch
        """
        raise NotImplementedError

    def create_new_commit(
        self, pr_info: PullRequestInfo, repo_info: RepositoryInfo
    ) -> None:
        """
        Create a new commit based on the info in PullRequestInfo
        """
        raise NotImplementedError

    def create_pull_request(
        self, branch_name: str, target_branch: str, title: str
    ) -> str:
        """
        Create a pull request on a VCS repository
        """
        raise NotImplementedError

    # def get_repo_url(self, url: str) -> str:
    #     """
    #     Returns the URL prefix for the specific repository
    #     :param url:
    #     :return:
    #     """
    #     raise NotImplementedError

    def disseminate_in_pull_request(self, pr_info: PullRequestInfo) -> str:
        """
        Create a pull request on a VCS repository
        """
        self.create_new_branch(pr_info.branch, self.repo_info.default_branch)
        try:
            self.create_new_commit(pr_info, self.repo_info)

            merge_request_url = self.create_pull_request(
                pr_info.branch,
                self.repo_info.default_branch,
                pr_info.commit_message,
            )
        except Exception as e:
            self.delete_branch(branch_name=pr_info.branch)
            raise e
        return merge_request_url
