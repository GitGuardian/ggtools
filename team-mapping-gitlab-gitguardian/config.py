import logging
import os

from pygitguardian.client import GGClient
from functools import cached_property
from dataclasses import dataclass

from pygitguardian.models import IncidentPermission


@dataclass
class Config:
    gitlab_token: str
    gitguardian_api_key: str
    gitguardian_url: str

    gitlab_url: str

    send_email: bool
    exclude_admin: bool
    default_incident_permission: IncidentPermission = IncidentPermission.EDIT
    logger_level: str = logging.INFO
    remove_members: bool = False
    pagination_size: int = 100

    @classmethod
    def from_env(cls):
        incident_permission = cls.default_incident_permission
        if incident_permission_env := os.environ.get("DEFAULT_INCIDENT_PERMISSION"):
            incident_permission = IncidentPermission(incident_permission_env)

        logger_level = logging._nameToLevel[
            os.environ.get("LOG_LEVEL", logging._levelToName[cls.logger_level])
        ]

        return cls(
            gitlab_token=os.environ["GITLAB_ACCESS_TOKEN"],
            gitguardian_api_key=os.environ["GITGUARDIAN_API_KEY"],
            gitlab_url=os.environ.get("GITLAB_URL", "https://gitlab.com"),
            gitguardian_url=os.environ.get(
                "GITGUARDIAN_INSTANCE", "https://api.gitguardian.com"
            ),
            send_email=os.environ.get("SEND_EMAIL", "True") == "True",
            exclude_admin=os.environ.get("EXCLUDE_ADMIN", "True") == "True",
            default_incident_permission=incident_permission,
            logger_level=logger_level,
        )

    @cached_property
    def client(self):
        return GGClient(api_key=self.gitguardian_api_key, base_uri=self.gitguardian_url)

    def __repr__(self):
        return (
            "Config("
            f"send_email={self.send_email}, "
            f"gitlab_url={self.gitlab_url}, "
            f"gitlab_token={self.gitlab_token}, "
            f"logger_level={logging._levelToName[self.logger_level]}, "
            f"exclude_admin={self.exclude_admin}, "
            f"remove_members={self.remove_members}, "
            f"gitguardian_url={self.gitguardian_url}, "
            f"gitguardian_api_key={self.gitguardian_api_key}, "
            f"default_incident_permission={self.default_incident_permission}"
            ")"
        )


CONFIG = Config.from_env()

if __name__ == "__main__":
    print(CONFIG)
