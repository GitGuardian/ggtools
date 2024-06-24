import random
import re
import string
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse


GITGUARDIAN_SAAS = "https://dashboard.gitguardian.com"
GITHUB_SAAS = "https://api.github.com"
GITLAB_SAAS = "https://gitlab.com"
ADO_SAAS = "https://dev.azure.com"
GITGUARDIAN_DOMAINS = ["gitguardian.com", "gitguardian.tech"]
ON_PREMISE_API_URL_PATH_PREFIX = "/exposed"


class MessageError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class HoneyTokenCreationError(MessageError):
    ...


class PullRequestCreationError(MessageError):
    ...


class CredentialsValidationError(MessageError):
    ...


class RepositoryAccessError(MessageError):
    ...


class BitBucketCloudNotSupportedError(Exception):
    ...


@dataclass
class RepositoryInfo:
    id: int | str
    name: str
    default_branch: str
    main_language: str | None


@dataclass
class PullRequestInfo:
    content: str
    commit_message: str
    branch: str
    filename: str


def generate_random_suffix() -> str:
    """
    Generate a random string of eight alphanumeric characters
    """
    letters_and_digits = string.ascii_letters + string.digits
    return "".join(random.choice(letters_and_digits) for _ in range(8))


def slugify(value):
    """
    Convert to ASCII. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-_")


def get_branch_name_from_commit_message(commit_message: str):
    return slugify(commit_message)[:255]


def get_saas_url_for_vcs(vcs: str):
    if vcs == "github":
        return GITHUB_SAAS
    elif vcs == "gitlab":
        return GITLAB_SAAS
    elif vcs == "ado":
        return ADO_SAAS
    elif vcs == "bitbucket":
        raise BitBucketCloudNotSupportedError
    else:
        raise NotImplementedError(f"Unsupported VCS: {vcs}")


def dashboard_to_api_url(dashboard_url: str) -> str:
    """
    Convert a dashboard URL to an API URL.
    """
    parsed_url = urlparse(dashboard_url.strip("/"))

    if any(parsed_url.netloc.endswith("." + domain) for domain in GITGUARDIAN_DOMAINS):
        parsed_url = parsed_url._replace(
            netloc=parsed_url.netloc.replace("dashboard", "api")
        )
    else:
        parsed_url = parsed_url._replace(
            path=f"{parsed_url.path}{ON_PREMISE_API_URL_PATH_PREFIX}"
        )
    return parsed_url.geturl()
