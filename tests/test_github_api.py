
import httpx
import pytest

from app.services.github_api import (
    GitHubAPI,
    GitHubAPIError,
    GitHubAuthenticationError,
    GitHubForbiddenError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubServerError,
    validate_repository,
    validate_username,
)


@pytest.mark.parametrize(
    "username",
    ["torvalds", "octocat", "python", "my-user"],
)
def test_valid_usernames(username: str) -> None:
    assert validate_username(username)


@pytest.mark.parametrize(
    "username",
    [
        "",
        "-invalid",
        "invalid-",
        "user name",
        "user/name",
        "a" * 40,
    ],
)
def test_invalid_usernames(username: str) -> None:
    assert not validate_username(username)


@pytest.mark.parametrize(
    "repository",
    ["cpython", "my-project", "project_name", "project.name"],
)
def test_valid_repository_names(repository: str) -> None:
    assert validate_repository(repository)


@pytest.mark.parametrize(
    "repository",
    [
        "",
        "invalid/repository",
        "repository name",
        "a" * 101,
    ],
)
def test_invalid_repository_names(repository: str) -> None:
    assert not validate_repository(repository)


async def make_api(handler, **kwargs) -> GitHubAPI:
    transport = httpx.MockTransport(handler)

    return GitHubAPI(
        base_url="https://api.github.test",
        timeout=2,
        transport=transport,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_get_user_and_cache() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1

        return httpx.Response(
            200,
            json={
                "login": "octocat",
                "followers": 10,
            },
        )

    api = await make_api(handler)

    try:
        first = await api.get_user("octocat")
        second = await api.get_user("octocat")

        assert first["login"] == "octocat"
        assert second["followers"] == 10
        assert calls == 1
    finally:
        await api.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "headers", "exception"),
    [
        (401, {}, GitHubAuthenticationError),
        (403, {}, GitHubForbiddenError),
        (404, {}, GitHubNotFoundError),
        (429, {}, GitHubRateLimitError),
        (
            403,
            {
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "1900000000",
            },
            GitHubRateLimitError,
        ),
        (500, {}, GitHubServerError),
        (400, {}, GitHubAPIError),
    ],
)
async def test_http_error_mapping(
    status,
    headers,
    exception,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            headers=headers,
            json={"message": "test error"},
        )

    api = await make_api(handler)

    try:
        with pytest.raises(exception):
            await api.get_user("octocat")
    finally:
        await api.close()


@pytest.mark.asyncio
async def test_invalid_json_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not-json",
        )

    api = await make_api(handler)

    try:
        with pytest.raises(
            GitHubAPIError,
            match="invalid response",
        ):
            await api.get_user("octocat")
    finally:
        await api.close()


@pytest.mark.asyncio
async def test_repository_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/python/cpython"

        return httpx.Response(
            200,
            json={"full_name": "python/cpython"},
        )

    api = await make_api(handler)

    try:
        result = await api.get_repository(
            "python",
            "cpython",
        )

        assert result["full_name"] == "python/cpython"
    finally:
        await api.close()


@pytest.mark.asyncio
async def test_user_repositories_pagination_parameters() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/users/octocat/repos"
        assert request.url.params["page"] == "2"
        assert request.url.params["per_page"] == "50"

        return httpx.Response(
            200,
            json=[{"name": "hello-world"}],
        )

    api = await make_api(handler)

    try:
        result = await api.get_user_repositories(
            "octocat",
            page=2,
            per_page=50,
        )

        assert result[0]["name"] == "hello-world"
    finally:
        await api.close()


@pytest.mark.asyncio
async def test_invalid_pagination_values() -> None:
    api = await make_api(
        lambda request: httpx.Response(200, json=[])
    )

    try:
        with pytest.raises(ValueError):
            await api.get_user_repositories(
                "octocat",
                page=0,
            )

        with pytest.raises(ValueError):
            await api.get_user_repositories(
                "octocat",
                per_page=101,
            )
    finally:
        await api.close()
