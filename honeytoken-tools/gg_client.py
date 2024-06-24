import requests
from client import ApiTokenClient
from common import (
    CredentialsValidationError,
    HoneyTokenCreationError,
    RepositoryInfo,
    generate_random_suffix,
)


class GGClient(ApiTokenClient):
    token_prefix = "Token"

    @property
    def common_url_path(self) -> str | None:
        return "v1"

    def validate_credentials(self):
        try:
            resp = self.get("health")
            if resp.status_code == 401:
                raise CredentialsValidationError(
                    f"Invalid GitGuardian token for {self.instance_url}"
                )
        except requests.exceptions.ConnectionError:
            raise CredentialsValidationError(
                f"Can't connect to GitGuardian at {self.instance_url}"
            )

    def create_honey_token_with_context(self, repo_info: RepositoryInfo):
        payload = {
            "type": "AWS",
            "name": f"{repo_info.name}-{generate_random_suffix()}",
            "description": f"Honeytoken deployed in {repo_info.name}",
        }

        if repo_info.main_language:
            payload["language"] = repo_info.main_language

        resp = self.post(
            "honeytokens/with-context",
            json=payload,
        )

        if not resp.ok:
            raise HoneyTokenCreationError(
                f"Can't create a honeytoken with context: {resp.json()['detail']}"
            )

        data = resp.json()
        return data

    def revoke_honey_token(self, honey_token_id: str) -> bool:
        resp = self.post(f"honeytokens/{honey_token_id}/revoke", {})
        return resp.ok
