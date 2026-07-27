"""Read-only GitHub repository access behind a protocol."""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Repository:
    name: str
    description: str | None
    language: str | None
    stars: int
    is_fork: bool
    size_kb: int
    pushed_at: str | None
    topics: list[str]


class GitHubUnavailable(Exception):
    """GitHub could not be reached, or the user does not exist."""


class GitHubClient(Protocol):
    async def repositories(self, username: str) -> list[Repository]: ...


class HTTPGitHubClient:
    """Public API only — no token required, so no user credentials are held."""

    BASE_URL = "https://api.github.com"

    def __init__(self, timeout_seconds: float = 10.0):
        self._timeout = timeout_seconds

    async def repositories(self, username: str) -> list[Repository]:
        import httpx

        params = {"per_page": 100, "sort": "pushed", "type": "owner"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self.BASE_URL}/users/{username}/repos",
                    params=params,
                    headers={"Accept": "application/vnd.github+json"},
                )
        except httpx.HTTPError as error:
            raise GitHubUnavailable(str(error)) from error
        if response.status_code == 404:
            raise GitHubUnavailable(f"no such GitHub user: {username}")
        if response.status_code != 200:
            raise GitHubUnavailable(f"GitHub returned {response.status_code}")
        return [
            Repository(
                name=item["name"],
                description=item.get("description"),
                language=item.get("language"),
                stars=item.get("stargazers_count", 0),
                is_fork=item.get("fork", False),
                size_kb=item.get("size", 0),
                pushed_at=item.get("pushed_at"),
                topics=item.get("topics", []),
            )
            for item in response.json()
        ]


class FakeGitHubClient:
    """Deterministic client for tests."""

    def __init__(self, repositories: dict[str, list[Repository]] | None = None):
        self.repositories_by_user = repositories or {}

    async def repositories(self, username: str) -> list[Repository]:
        if username not in self.repositories_by_user:
            raise GitHubUnavailable(f"no such GitHub user: {username}")
        return self.repositories_by_user[username]


def build_github_client() -> GitHubClient:
    return HTTPGitHubClient()
