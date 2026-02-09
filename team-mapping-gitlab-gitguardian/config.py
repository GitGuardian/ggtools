import logging
import os

from pygitguardian.client import GGClient
from functools import cached_property
from dataclasses import dataclass
from urllib.parse import urlparse

from pygitguardian.models import IncidentPermission

GG_SAAS_HOSTNAMES = {"api.gitguardian.com", "dashboard.gitguardian.com"}
GG_EU_SAAS_HOSTNAMES = {"api.eu1.gitguardian.com", "dashboard.eu1.gitguardian.com"}


@dataclass
class Config:
    gitlab_token: str
    gitguardian_api_key: str
    gitguardian_url: str

    gitlab_url: str

    send_email: bool
    gitlab_level: int = 30  # 30 = DEVELOPER
    invite_domains: set[str] | None = None
    default_incident_permission: IncidentPermission = IncidentPermission.EDIT
    logger_level: int = logging.INFO
    remove_members: bool = False
    pagination_size: int = 100

    @classmethod
    def from_env(cls):
        incident_permission = cls.default_incident_permission
        if incident_permission_env := os.environ.get("DEFAULT_INCIDENT_PERMISSION"):
            incident_permission = IncidentPermission(incident_permission_env)

        logger_level = cls.logger_level
        if logger_level_name := os.environ.get("LOG_LEVEL"):
            logger_level = getattr(logging, logger_level_name.upper())

        gitlab_level = cls.gitlab_level
        if gitlab_level_env := os.environ.get("GITLAB_LEVEL"):
            gitlab_level = int(gitlab_level_env)

        invite_domains = {
            domain.strip()
            for domain in os.environ.get("INVITE_DOMAINS", "").split(",")
            if len(domain.strip())
        }

        return cls(
            gitlab_token=os.environ["GITLAB_ACCESS_TOKEN"],
            gitguardian_api_key=os.environ["GITGUARDIAN_API_KEY"],
            gitlab_url=os.environ.get("GITLAB_URL", "https://gitlab.com"),
            gitguardian_url=os.environ.get(
                "GITGUARDIAN_INSTANCE", "https://api.gitguardian.com"
            ),
            send_email=os.environ.get("SEND_EMAIL", "True") == "True",
            invite_domains=invite_domains,
            default_incident_permission=incident_permission,
            logger_level=logger_level,
            gitlab_level=gitlab_level,
        )

    @cached_property
    def client(self):
        parsed = urlparse(self.gitguardian_url)
        if parsed.hostname in GG_SAAS_HOSTNAMES:
            gitguardian_url = "https://api.gitguardian.com"
        elif parsed.hostname in GG_EU_SAAS_HOSTNAMES:
            gitguardian_url = "https://api.eu1.gitguardian.com"
        else:
            gitguardian_url = f"{parsed.scheme}://{parsed.hostname}/exposed"
        return GGClient(api_key=self.gitguardian_api_key, base_uri=gitguardian_url)

    def __repr__(self):
        return (
            "Config("
            f"send_email={self.send_email}, "
            f"invite_domains={self.invite_domains}, "
            f"gitlab_url={self.gitlab_url}, "
            f"gitlab_token={self.gitlab_token}, ",
            f"gitlab_level={self.gitlab_level}, ",
            f"logger_level={logging._levelToName[self.logger_level]}, "
            f"remove_members={self.remove_members}, "
            f"gitguardian_url={self.gitguardian_url}, "
            f"gitguardian_api_key={self.gitguardian_api_key}, "
            f"default_incident_permission={self.default_incident_permission}"
            ")"
        )


CONFIG = Config.from_env()

if __name__ == "__main__":
    print(CONFIG)
