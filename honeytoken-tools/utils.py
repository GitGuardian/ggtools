from base64 import b64encode

from ado import ADOClient, ADORepoClient
from bitbucket import BitBucketClient, BitBucketRepoClient
from client import VCSClient
from common import RepositoryInfo
from github import GitHubClient, GitHubRepoClient
from gitlab import GitLabClient, GitLabRepoClient


def get_client_for_vcs(vcs: str, url: str, token: str):
    if vcs == "github":
        return GitHubClient(url, token)
    elif vcs == "gitlab":
        return GitLabClient(url, token)
    elif vcs == "ado":
        token = b64encode(f":{token}".encode()).decode()
        return ADOClient(url, token)
    elif vcs == "bitbucket":
        return BitBucketClient(url, token)
    else:
        raise NotImplementedError(f"Unsupported VCS: {vcs}")


def get_repository_client_from_vcs_client(
    vcs_client: VCSClient, repo_info: RepositoryInfo
):
    if isinstance(vcs_client, GitHubClient):
        repo_client_cls = GitHubRepoClient
    elif isinstance(vcs_client, GitLabClient):
        repo_client_cls = GitLabRepoClient
    elif isinstance(vcs_client, ADOClient):
        repo_client_cls = ADORepoClient
    elif isinstance(vcs_client, BitBucketClient):
        repo_client_cls = BitBucketRepoClient
    else:
        raise NotImplementedError(f"Unsupported VCS: {type(vcs_client)}")

    return repo_client_cls(
        repo_info, vcs_client.instance_url, vcs_client.instance_token
    )
