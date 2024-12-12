import os


class Config:
    def _ensure_env(self, env_var_name: str) -> str:
        return os.environ[env_var_name]

    def _env(self, env_var_name: str) -> str | None:
        return os.environ.get(env_var_name)

    @property
    def gitguardian_token(self) -> str:
        return self._ensure_env("GITGUARDIAN_TOKEN")

    @property
    def gitguardian_instance(self) -> str | None:
        return self._env("GITGUARDIAN_INSTANCE")

    @property
    def github_token(self) -> str:
        return self._ensure_env("GITHUB_TOKEN")

    @property
    def github_org(self) -> str:
        return self._ensure_env("GITHUB_ORG")

    @property
    def github_instance(self) -> str | None:
        return self._env("GITHUB_INSTANCE")
