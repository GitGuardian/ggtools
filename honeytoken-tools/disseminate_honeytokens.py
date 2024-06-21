import argparse
import json
import os

from common import (
    GITGUARDIAN_SAAS,
    BitBucketCloudNotSupportedError,
    CredentialsValidationError,
    HoneyTokenCreationError,
    PullRequestCreationError,
    PullRequestInfo,
    RepositoryAccessError,
    RepositoryInfo,
    dashboard_to_api_url,
    get_branch_name_from_commit_message,
    get_saas_url_for_vcs,
)
from gg_client import GGClient

from utils import get_client_for_vcs, get_repository_client_from_vcs_client


def parse_vcs_url(vcs_url: str | None, vcs: str) -> str | None:
    if not vcs_url:
        vcs_url = os.getenv("VCS_URL")
        if not vcs_url:
            vcs_url = get_saas_url_for_vcs(vcs)
    return vcs_url.strip("/")


def parse_gitguardian_url(gitguardian_url: str | None) -> str | None:
    if not gitguardian_url:
        gitguardian_url = os.getenv("GITGUARDIAN_URL")
        if not gitguardian_url:
            gitguardian_url = GITGUARDIAN_SAAS
    return gitguardian_url.strip("/")


def validate_parameters(args: argparse.Namespace, parser: argparse.ArgumentParser):
    try:
        vcs_url = parse_vcs_url(args.vcs_url, args.vcs)
    except BitBucketCloudNotSupportedError:
        parser.error(
            "BitBucket Cloud is not supported. Use VCS_URL to provide your BitBucket Server instance."
        )

    vcs_token = os.getenv("VCS_TOKEN")

    if not vcs_token:
        parser.error(
            "VCS token is required. Configure it via environment variable VCS_TOKEN."
        )

    gitguardian_url = parse_gitguardian_url(args.gitguardian_url)
    gitguardian_token = os.getenv("GITGUARDIAN_TOKEN")

    if not gitguardian_token:
        parser.error(
            "GitGuardian access token is required. Configure it via environment variable GITGUARDIAN_TOKEN."
        )

    repos_names = []
    for value in args.repo_names:
        if "," in value:
            repos_names.extend(value.split(","))
        else:
            repos_names.append(value)

    return vcs_url, vcs_token, gitguardian_url, gitguardian_token, repos_names


def main():
    parser = argparse.ArgumentParser(
        description="Script to disseminate honeytokens in your repositories via pull requests."
    )

    parser.add_argument(
        "--vcs",
        choices=["github", "gitlab", "ado", "bitbucket"],
        required=True,
        help="Version control system",
    )
    parser.add_argument(
        "--vcs-url",
        help="VCS instance URL. If omitted, the default VCS URL will be used. "
        "Can be also configured via environment variable VCS_URL.",
    )
    parser.add_argument(
        "--gitguardian-url",
        help="GitGuardian instance URL. If omitted, https://dashboard.gitguardian.com "
        "will be used. Can be also configured via environment variable GITGUARDIAN_URL.",
    )
    parser.add_argument(
        "--repo-names",
        nargs="+",
        required=True,
        help="Comma-separated or space-separated list of repository names",
    )
    parser.add_argument(
        "--output", choices=["json", "text"], default="text", help="Output format"
    )

    args = parser.parse_args()

    (
        vcs_url,
        vcs_token,
        gitguardian_url,
        gitguardian_token,
        repos_names,
    ) = validate_parameters(args, parser)

    try:
        vcs_client = get_client_for_vcs(args.vcs, vcs_url, vcs_token)
        vcs_client.validate_credentials()

        # validate access to all the repositories
        vcs_repos = [vcs_client.get_repository_info(repo) for repo in repos_names]

        gg_client = GGClient(dashboard_to_api_url(gitguardian_url), gitguardian_token)
        gg_client.validate_credentials()

        disseminate_honeytokens(vcs_client, gg_client, vcs_repos, args.output)

    except (CredentialsValidationError, RepositoryAccessError) as error:
        parser.error(error.message)


def disseminate_honeytokens(
    vcs_client, gg_client: GGClient, repos: list[RepositoryInfo], output: str
):
    result_output = dict()
    for repo in repos:
        result_output[repo.name] = {
            "url": "",
            "ok": True,
            "error": "",
            "honeytoken_id": "",
        }

        # 1. create a honeytoken with context
        try:
            error_msg = None
            data = gg_client.create_honey_token_with_context(repo)
        except HoneyTokenCreationError as error:
            error_msg = error.message
        except Exception as error:
            error_msg = type(error).__name__ + ": " + str(error)

        if error_msg:
            result_output[repo.name]["ok"] = False
            result_output[repo.name][
                "error"
            ] = f"Failed to create a honeytoken: {error_msg}"
            continue

        # 2. create pull request
        pr_info = PullRequestInfo(
            content=data["content"],
            commit_message=data["suggested_commit_message"],
            branch=get_branch_name_from_commit_message(
                data["suggested_commit_message"]
            ),
            filename=data["filename"],
        )

        honey_token_id = data["honeytoken_id"]
        result_output[repo.name]["honeytoken_id"] = honey_token_id

        try:
            error_msg = None
            repo_client = get_repository_client_from_vcs_client(vcs_client, repo)
            pull_request_url = repo_client.disseminate_in_pull_request(pr_info)
        except PullRequestCreationError as error:
            error_msg = error.message
        except Exception as error:
            error_msg = type(error).__name__ + ": " + str(error)

        if error_msg:
            ht_revoked = gg_client.revoke_honey_token(honey_token_id)
            result_output[repo.name]["ok"] = False
            result_output[repo.name]["error"] = (
                f"Failed to disseminate honeytoken. {error_msg}. Honeytoken {honey_token_id} was created "
                + ("but revoked." if ht_revoked else "and not revoked.")
            )
            continue

        result_output[repo.name]["url"] = pull_request_url

    if output == "json":
        print(json.dumps(result_output, indent=2))
    else:
        successful_results = [
            repo for repo in result_output if result_output[repo]["ok"]
        ]
        failed_results = [
            repo for repo in result_output if not result_output[repo]["ok"]
        ]

        if successful_results:
            print("Honeytokens successfully disseminated in:")
            for repo in successful_results:
                print(f"{repo}: {result_output[repo]['url']}")

        if failed_results:
            print("Could not disseminate in:")
            for repo in failed_results:
                print(f"{repo}: {result_output[repo]['error']}")


if __name__ == "__main__":
    main()
