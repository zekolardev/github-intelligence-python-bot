
import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


class GitHubAPIError(Exception):
    """Base exception for GitHub API failures."""


class GitHubNotFoundError(GitHubAPIError):
    pass


class GitHubRateLimitError(GitHubAPIError):
    def __init__(self, message: str, reset_at: int | None = None):
        super().__init__(message)
        self.reset_at = reset_at


class GitHubAuthenticationError(GitHubAPIError):
    pass


class GitHubForbiddenError(GitHubAPIError):
    pass


class GitHubServerError(GitHubAPIError):
    pass


@dataclass
class CacheEntry:
    expires_at: float
    value: dict[str, Any]


def validate_username(username: str) -> bool:
    return bool(USERNAME_PATTERN.fullmatch(username))


def validate_repository(repository: str) -> bool:
    return bool(REPOSITORY_PATTERN.fullmatch(repository))


class GitHubAPI:
    def __init__(
        self,
        base_url: str,
        timeout: float,
        token: str | None = None,
        cache_ttl: int = 300,
        cache_max_entries: int = 256,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GitHub-Intelligence-Bot",
        }

        if token:
            headers["Authorization"] = f"Bearer {token}"

        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

        self.cache_ttl = max(0, cache_ttl)
        self.cache_max_entries = max(1, cache_max_entries)
        self._cache: dict[str, CacheEntry] = {}
        self._cache_lock = asyncio.Lock()

    async def close(self) -> None:
        await self.client.aclose()

    def clear_cache(self) -> None:
        self._cache.clear()

    async def _get_cached(self, key: str) -> dict[str, Any] | None:
        async with self._cache_lock:
            entry = self._cache.get(key)

            if entry is None:
                return None

            if entry.expires_at <= time.monotonic():
                self._cache.pop(key, None)
                return None

            return entry.value.copy()

    async def _set_cache(self, key: str, value: dict[str, Any]) -> None:
        if self.cache_ttl <= 0:
            return

        async with self._cache_lock:
            now = time.monotonic()

            expired = [
                cache_key
                for cache_key, entry in self._cache.items()
                if entry.expires_at <= now
            ]

            for old_key in expired:
                self._cache.pop(old_key, None)

            if (
                key not in self._cache
                and len(self._cache) >= self.cache_max_entries
            ):
                oldest_key = min(
                    self._cache,
                    key=lambda cache_key: self._cache[cache_key].expires_at,
                )
                self._cache.pop(oldest_key, None)

            self._cache[key] = CacheEntry(
                expires_at=now + self.cache_ttl,
                value=value.copy(),
            )

    @staticmethod
    def _rate_limit_reset(response: httpx.Response) -> int | None:
        value = response.headers.get("X-RateLimit-Reset")

        try:
            return int(value) if value else None
        except ValueError:
            return None

    async def _get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cache_key = f"{endpoint}?{httpx.QueryParams(params or {})}"

        cached = await self._get_cached(cache_key)

        if cached is not None:
            logger.debug("GitHub cache hit: %s", endpoint)
            return cached

        try:
            response = await self.client.get(endpoint, params=params)
        except httpx.TimeoutException as exc:
            raise GitHubAPIError(
                "GitHub did not respond in time."
            ) from exc
        except httpx.RequestError as exc:
            raise GitHubAPIError(
                "Could not connect to GitHub."
            ) from exc

        status = response.status_code

        if status == 404:
            raise GitHubNotFoundError(
                "The requested GitHub resource was not found."
            )

        if status == 401:
            raise GitHubAuthenticationError(
                "GitHub rejected the authentication token."
            )

        if status in (403, 429):
            remaining = response.headers.get("X-RateLimit-Remaining")
            retry_after = response.headers.get("Retry-After")
            reset_at = self._rate_limit_reset(response)

            if status == 429 or remaining == "0" or retry_after is not None:
                raise GitHubRateLimitError(
                    "GitHub API rate limit exceeded.",
                    reset_at=reset_at,
                )

            raise GitHubForbiddenError(
                "GitHub denied access to this resource."
            )

        if status >= 500:
            raise GitHubServerError(
                f"GitHub server error (HTTP {status})."
            )

        if status >= 400:
            raise GitHubAPIError(
                f"GitHub API returned HTTP {status}."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise GitHubAPIError(
                "GitHub returned an invalid response."
            ) from exc

        if not isinstance(data, (dict, list)):
            raise GitHubAPIError(
                "Unexpected GitHub API response."
            )

        if isinstance(data, dict):
            await self._set_cache(cache_key, data)

        return data

    async def get_user(self, username: str) -> dict[str, Any]:
        if not validate_username(username):
            raise ValueError("Invalid GitHub username.")

        data = await self._get(f"/users/{username}")

        if not isinstance(data, dict):
            raise GitHubAPIError(
                "Unexpected GitHub user response."
            )

        return data

    async def get_repository(
        self,
        owner: str,
        repository: str,
    ) -> dict[str, Any]:
        if not validate_username(owner):
            raise ValueError("Invalid repository owner.")

        if not validate_repository(repository):
            raise ValueError("Invalid repository name.")

        data = await self._get(f"/repos/{owner}/{repository}")

        if not isinstance(data, dict):
            raise GitHubAPIError(
                "Unexpected GitHub repository response."
            )

        return data

    async def get_user_repositories(
        self,
        username: str,
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        if not validate_username(username):
            raise ValueError("Invalid GitHub username.")

        if page < 1:
            raise ValueError("Page must be greater than zero.")

        if not 1 <= per_page <= 100:
            raise ValueError("per_page must be between 1 and 100.")

        data = await self._get(
            f"/users/{username}/repos",
            params={
                "page": page,
                "per_page": per_page,
                "sort": "updated",
            },
        )

        if not isinstance(data, list):
            raise GitHubAPIError(
                "Unexpected GitHub repositories response."
            )

        return [
            item
            for item in data
            if isinstance(item, dict)
        ]
