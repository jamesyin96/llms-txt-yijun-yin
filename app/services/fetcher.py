"""Shared HTTP fetching layer for crawler modules.

All crawler network requests should go through this module. It centralizes the
operational rules from the implementation plan: safety checks, same-host
redirect validation, timeout, retry/backoff, user-agent, content type capture,
and maximum response size enforcement.
"""

from dataclasses import dataclass
import time
from urllib.parse import urljoin, urlparse

import httpx

from app.config import USER_AGENT
from app.services import security
from app.services.security import UrlSafetyPolicy


DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 0.25
RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    """Raised when a URL cannot be fetched after retries."""


class TooManyRedirectsError(FetchError):
    """Raised when a response redirects more than the configured limit."""


class ResponseTooLargeError(FetchError):
    """Raised when a response exceeds the configured byte limit."""


class RetriableStatusError(FetchError):
    """Internal signal used to retry transient HTTP statuses."""


@dataclass(frozen=True)
class FetchConfig:
    """Runtime settings for one fetch operation."""

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS
    user_agent: str = USER_AGENT
    safety_policy: UrlSafetyPolicy = UrlSafetyPolicy()
    resolve_host: bool = True


@dataclass(frozen=True)
class FetchResult:
    """HTTP response data returned to crawler/parser modules."""

    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    content: bytes
    redirect_count: int

    @property
    def text(self) -> str:
        """Best-effort UTF-8 text decoding for HTML/XML/robots parsing."""

        return self.content.decode("utf-8", errors="replace")


def fetch_url(
    url: str,
    *,
    config: FetchConfig | None = None,
    client: httpx.Client | None = None,
) -> FetchResult:
    """Fetch a URL with safety checks, manual redirects, retries, and limits."""

    fetch_config = config or FetchConfig()
    security.assert_safe_url(url, resolve_host=fetch_config.resolve_host)

    owns_client = client is None
    http_client = client or httpx.Client(follow_redirects=False)
    try:
        return _fetch_with_redirects(url, fetch_config, http_client)
    finally:
        if owns_client:
            http_client.close()


def _fetch_with_redirects(
    url: str,
    config: FetchConfig,
    client: httpx.Client,
) -> FetchResult:
    requested_url = url
    current_url = url
    redirect_count = 0

    while True:
        response_data = _request_with_retries(current_url, config, client)
        status_code = response_data.status_code

        if _is_redirect_status(status_code):
            location = response_data.headers.get("location")
            if not location:
                raise FetchError("Redirect response did not include a Location header.")
            if redirect_count >= config.safety_policy.max_redirects:
                raise TooManyRedirectsError("Too many redirects while fetching URL.")

            current_url = _validate_redirect(
                current_url,
                location,
                resolve_host=config.resolve_host,
            )
            redirect_count += 1
            continue

        return FetchResult(
            requested_url=requested_url,
            final_url=response_data.final_url,
            status_code=status_code,
            content_type=response_data.headers.get("content-type", ""),
            content=response_data.content,
            redirect_count=redirect_count,
        )


@dataclass(frozen=True)
class _ResponseData:
    final_url: str
    status_code: int
    headers: httpx.Headers
    content: bytes


def _request_with_retries(
    url: str,
    config: FetchConfig,
    client: httpx.Client,
) -> _ResponseData:
    last_error: Exception | None = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            response_data = _request_once(url, config, client)
            if response_data.status_code in RETRIABLE_STATUS_CODES:
                raise RetriableStatusError(
                    f"Received retriable HTTP status {response_data.status_code}."
                )
            return response_data
        except (httpx.TimeoutException, httpx.TransportError, RetriableStatusError) as exc:
            last_error = exc
            if attempt == config.max_attempts:
                break
            _sleep_before_retry(attempt, config.backoff_seconds)

    raise FetchError(f"Could not fetch URL after {config.max_attempts} attempts.") from last_error


def _request_once(
    url: str,
    config: FetchConfig,
    client: httpx.Client,
) -> _ResponseData:
    headers = {"User-Agent": config.user_agent}

    with client.stream(
        "GET",
        url,
        headers=headers,
        timeout=config.timeout_seconds,
        follow_redirects=False,
    ) as response:
        if _is_redirect_status(response.status_code):
            return _ResponseData(
                final_url=str(response.url),
                status_code=response.status_code,
                headers=response.headers,
                content=b"",
            )
        if response.status_code in RETRIABLE_STATUS_CODES:
            return _ResponseData(
                final_url=str(response.url),
                status_code=response.status_code,
                headers=response.headers,
                content=b"",
            )

        return _ResponseData(
            final_url=str(response.url),
            status_code=response.status_code,
            headers=response.headers,
            content=_read_limited(response, config.safety_policy.max_response_bytes),
        )


def _read_limited(response: httpx.Response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0

    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise ResponseTooLargeError("Response exceeded maximum allowed size.")
        chunks.append(chunk)

    return b"".join(chunks)


def _validate_redirect(source_url: str, redirect_url: str, *, resolve_host: bool) -> str:
    absolute_redirect = urljoin(source_url, redirect_url)
    source_hostname = urlparse(source_url).hostname
    security.assert_safe_url(
        absolute_redirect,
        allowed_hostname=source_hostname,
        resolve_host=resolve_host,
    )
    return absolute_redirect


def _is_redirect_status(status_code: int) -> bool:
    return status_code in {301, 302, 303, 307, 308}


def _sleep_before_retry(attempt: int, backoff_seconds: float) -> None:
    if backoff_seconds <= 0:
        return
    time.sleep(backoff_seconds * (2 ** (attempt - 1)))
