import re
from typing import Any, Iterable

import requests

SAAS_INSTANCES = {
    "https://dashboard.gitguardian.com",
    "https://api.gitguardian.com",
}


class GitGuardianApiClient:
    def __init__(self, api_token, instance=None):
        if instance is None or any(instance.startswith(i) for i in SAAS_INSTANCES):
            self._base_url = "https://api.gitguardian.com/v1"
        else:
            self._base_url = f"{instance}/exposed/v1"

        self._session = requests.Session()
        self._session.headers.update({"authorization": f"Token {api_token}"})

    def _url(self, endpoint):
        return f"{self._base_url}{endpoint}"

    def _get_url(self, url):
        resp = self._session.get(url)
        resp.raise_for_status()
        return resp

    def _get(self, endpoint, **params):
        resp = self._session.get(self._url(endpoint), params=params)
        resp.raise_for_status()
        return resp

    def _post(self, endpoint, **json):
        json = {k: v for k, v in json.items() if v is not None}
        resp = self._session.post(self._url(endpoint), json=json)
        resp.raise_for_status()
        return resp

    def _patch(self, endpoint, **json):
        json = {k: v for k, v in json.items() if v is not None}
        resp = self._session.patch(self._url(endpoint), json=json)
        resp.raise_for_status()
        return resp

    def _get_paginated(self, endpoint, per_page=100, **params):
        params.update(per_page=per_page)
        page = self._get(endpoint, **params)
        yield page
        while True:
            if "next" not in page.links:
                break
            page = self._get_url(page.links["next"]["url"])
            yield page

    def get_health(self):
        return self._get("/health").json()

    def get_api_token(self):
        return self._get("/api_tokens/self").json()

    # Sources
    def get_sources(self, _type=None):
        params = {}
        if _type is not None:
            params["type"] = _type
        for page in self._get_paginated("/sources", **params):
            yield from page.json()

    def get_github_sources(self):
        for page in self._get_paginated("/sources", _type="github"):
            yield from page.json()

    # Teams
    def get_teams(self, is_global=None):
        params = {}
        if is_global is not None:
            params["is_global"] = "true" if is_global else "false"
        for page in self._get_paginated("/teams", **params):
            yield from page.json()

    def create_team(self, name, description=None):
        return self._post("/teams", name=name, description=description).json()

    def update_team(self, team, name, description=None):
        return self._patch(
            f"/teams/{team.id}", name=name, description=description
        ).json()

    def get_team_sources(self, team):
        return self._get(f"/teams/{team.id}/sources").json()

    def update_team_sources(self, team, sources_to_add=None, sources_to_remove=None):
        sources_to_add = list(sources_to_add) if sources_to_add else []
        sources_to_remove = list(sources_to_remove) if sources_to_remove else []
        return self._post(
            f"/teams/{team.id}/sources",
            sources_to_add=sources_to_add,
            sources_to_remove=sources_to_remove,
        )


class GitGuardianClient(GitGuardianApiClient):
    _teams_by_id: dict[int, "GitGuardianTeam"]
    _teams_by_github_id: dict[int, "GitGuardianTeam"]
    _sources_by_id: dict[int, "GitGuardianSource"]
    _sources_by_github_id: dict[int, "GitGuardianSource"]

    def ensure_healthy(self):
        self.get_health()
        return self

    def ensure_scopes(self, required_scopes=None):
        token_info = self.get_api_token()
        scopes = set(token_info["scopes"])
        if required_scopes != required_scopes & scopes:
            missing_scopes = required_scopes - scopes
            raise SystemExit(
                f"Missing scopes on GitGuardian API token: {missing_scopes}"
            )
        return self

    def _by_id_and_github_id(
        self, cls, raw_objs: Iterable[dict[str, Any]], by_id: dict, by_github_id: dict
    ):
        for raw_obj in raw_objs:
            obj = cls(raw_data=raw_obj, gitguardian=self)
            by_id[obj.id] = obj
            by_github_id[obj.github_id] = obj

    def load_teams(self):
        self._teams_by_id = {}
        self._teams_by_github_id = {}

        self._by_id_and_github_id(
            GitGuardianTeam,
            self.get_teams(is_global=False),
            self._teams_by_id,
            self._teams_by_github_id,
        )

        return self

    def load_sources(self):
        self._sources_by_id = {}
        self._sources_by_github_id = {}

        self._by_id_and_github_id(
            GitGuardianSource,
            self.get_github_sources(),
            self._sources_by_id,
            self._sources_by_github_id,
        )

        return self

    def _update_from_team(self, team):
        self._teams_by_id[team.id] = team
        self._teams_by_github_id[team.github_id] = team
        return team

    def team_by_github_id(self, github_id: int):
        return self._teams_by_github_id.get(github_id)

    def source_by_github_repo_id(self, github_id: int):
        return self._sources_by_github_id.get(github_id)

    def sources_by_github_repo_ids(self, github_repo_ids: list[int]):
        for github_repo_id in github_repo_ids:
            source = self.source_by_github_repo_id(github_repo_id)
            if source is not None:
                yield source

    def sources_ids_by_github_repo_ids(self, github_repo_ids: list[int]):
        for source in self.sources_by_github_repo_ids(github_repo_ids):
            yield source.id

    def create_or_sync_team(self, display_name, github_id, github_description):
        if github_description:
            description = f"{github_description} / GH({github_id})"
        else:
            description = f"GH({github_id})"

        team = self.team_by_github_id(github_id)
        if team:
            if (team.name == display_name) and (team.description == description):
                return team

            raw_team = team.update(
                name=display_name,
                description=description,
            )
        else:
            raw_team = self.create_team(
                name=display_name,
                description=description,
            )

        return self._update_from_team(
            GitGuardianTeam(
                raw_data=raw_team,
                gitguardian=self,
            )
        )


class GitHubSyncedObj:
    _github_id: int | None = None

    @property
    def github_id(self) -> int | None:
        if self._github_id is None:
            self._github_id = self._parse_github_id()
        return self._github_id

    def _parse_github_id(self) -> int | None:
        raise NotImplementedError("_parse_github_id must be implemented by subclasses")


class GitGuardianObj:
    def __init__(self, raw_data: dict[str, Any], gitguardian: GitGuardianClient):
        self._gitguardian = gitguardian
        self._raw_data = raw_data

    @property
    def id(self) -> int:
        return self._raw_data["id"]


class GitGuardianTeam(GitGuardianObj, GitHubSyncedObj):
    @property
    def name(self) -> str:
        return self._raw_data["name"]

    @property
    def description(self) -> str:
        return self._raw_data["description"]

    def _parse_github_id(self) -> int | None:
        github_id_re = re.compile(r".*GH\((?P<id>[0-9]+)\).*")
        if match := github_id_re.match(self.description):
            return int(match["id"])
        return None

    def update(self, name, description=None):
        return self._gitguardian.update_team(
            team=self,
            name=name,
            description=description,
        )

    def github_sources(self):
        for raw_source in self._gitguardian.get_team_sources(team=self):
            source = GitGuardianSource(
                raw_data=raw_source, gitguardian=self._gitguardian
            )
            yield source

    def update_sources(self, github_repo_ids):
        github_repo_ids = set(github_repo_ids)
        gitguardian_github_repos = set(s.github_id for s in self.github_sources())

        self._gitguardian.update_team_sources(
            team=self,
            sources_to_add=self._gitguardian.sources_ids_by_github_repo_ids(
                github_repo_ids=github_repo_ids - gitguardian_github_repos
            ),
            sources_to_remove=self._gitguardian.sources_ids_by_github_repo_ids(
                github_repo_ids=gitguardian_github_repos - github_repo_ids
            ),
        )


class GitGuardianSource(GitGuardianObj, GitHubSyncedObj):
    @property
    def type(self) -> str:
        return self._raw_data["type"]

    @property
    def external_id(self) -> int:
        return int(self._raw_data["external_id"])

    def _parse_github_id(self) -> int | None:
        if self.type == "github":
            return self.external_id
        return None
