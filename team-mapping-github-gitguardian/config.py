import os
import logging
from functools import cached_property
from pygitguardian.client import GGClient
from github import Auth, Github, GithubRetry


class Config:
    def _ensure_env(self, env_var_name: str) -> str:
        return os.environ[env_var_name]

    def _env(self, env_var_name: str, default_value: str | None = None) -> str | None:
        return os.environ.get(env_var_name) or default_value

    @property
    def gitguardian_token(self) -> str:
        return self._ensure_env("GITGUARDIAN_TOKEN")

    @property
    def gitguardian_instance(self) -> str:
        return self._env("GITGUARDIAN_INSTANCE", "https://api.gitguardian.com")

    @property
    def github_token(self) -> str:
        return self._ensure_env("GITHUB_TOKEN")

    @property
    def github_org(self) -> str:
        return self._ensure_env("GITHUB_ORG")

    @property
    def github_instance(self) -> str:
        return self._env("GITHUB_INSTANCE", "https://api.github.com")

    @property
    def logger_level(self) -> int:
        if level := self._env("LEVEL"):
            return logging._nameToLevel[level]
        return logging.INFO

    @property
    def email_blacklist(self) -> list[str]:
        return []

    @property
    def notify_users(self) -> bool:
        if value := self._env("NOTIFY_USER"):
            return value.lower() == "true"
        return True

    @cached_property
    def gg_client(self) -> GGClient:
        return GGClient(
            api_key=self.gitguardian_token,
            base_uri=self.gitguardian_instance,
        )

    @cached_property
    def github_client(self) -> Github:
        return Github(
            base_url=self.github_instance,
            auth=Auth.Token(self.github_token),
            retry=GithubRetry(),
        )


CONFIG = Config()
