import httpx
import pytest

from app.services.fetcher import (
    FetchConfig,
    FetchError,
    ResponseTooLargeError,
    TooManyRedirectsError,
    fetch_url,
)
from app.services.security import UnsafeUrlError, UrlSafetyPolicy


def test_fetch_success_captures_response_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "test-agent"
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<h1>Hello</h1>",
            request=request,
        )

    result = fetch_url(
        "https://example.com/",
        config=FetchConfig(user_agent="test-agent", resolve_host=False),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert result.requested_url == "https://example.com/"
    assert result.final_url == "https://example.com/"
    assert result.status_code == 200
    assert result.content_type == "text/html; charset=utf-8"
    assert result.content == b"<h1>Hello</h1>"
    assert result.text == "<h1>Hello</h1>"
    assert result.redirect_count == 0


def test_fetch_retries_transient_statuses() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, request=request)
        return httpx.Response(200, content=b"ok", request=request)

    result = fetch_url(
        "https://example.com/",
        config=FetchConfig(backoff_seconds=0, resolve_host=False),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert attempts == 3
    assert result.content == b"ok"


def test_fetch_retries_transport_errors() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("temporary failure", request=request)
        return httpx.Response(200, content=b"ok", request=request)

    result = fetch_url(
        "https://example.com/",
        config=FetchConfig(backoff_seconds=0, resolve_host=False),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert attempts == 3
    assert result.status_code == 200


def test_fetch_raises_after_attempts_are_exhausted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("still down", request=request)

    with pytest.raises(FetchError):
        fetch_url(
            "https://example.com/",
            config=FetchConfig(max_attempts=2, backoff_seconds=0, resolve_host=False),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )


def test_fetch_blocks_unsafe_url_before_request() -> None:
    requested = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requested
        requested = True
        return httpx.Response(200, request=request)

    with pytest.raises(UnsafeUrlError):
        fetch_url(
            "http://127.0.0.1/",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    assert requested is False


def test_fetch_allows_same_host_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(302, headers={"location": "/final"}, request=request)
        return httpx.Response(200, content=b"final", request=request)

    result = fetch_url(
        "https://example.com/",
        config=FetchConfig(resolve_host=False),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert result.final_url == "https://example.com/final"
    assert result.redirect_count == 1
    assert result.content == b"final"


def test_fetch_blocks_redirect_to_localhost() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/admin"},
            request=request,
        )

    with pytest.raises(UnsafeUrlError):
        fetch_url(
            "https://example.com/",
            config=FetchConfig(resolve_host=False),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )


def test_fetch_blocks_cross_host_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "https://other.example.com/"},
            request=request,
        )

    with pytest.raises(UnsafeUrlError):
        fetch_url(
            "https://example.com/",
            config=FetchConfig(resolve_host=False),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )


def test_fetch_blocks_too_many_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"}, request=request)

    with pytest.raises(TooManyRedirectsError):
        fetch_url(
            "https://example.com/",
            config=FetchConfig(
                resolve_host=False,
                safety_policy=UrlSafetyPolicy(max_redirects=1),
            ),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )


def test_fetch_blocks_oversized_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"too large", request=request)

    with pytest.raises(ResponseTooLargeError):
        fetch_url(
            "https://example.com/",
            config=FetchConfig(
                resolve_host=False,
                safety_policy=UrlSafetyPolicy(max_response_bytes=4),
            ),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

