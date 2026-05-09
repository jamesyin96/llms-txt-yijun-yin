"""Security checks for user-submitted and crawler-discovered URLs.

The crawler will eventually fetch arbitrary URLs supplied by users, so all
network-bound URLs must pass through this module first. The checks here focus
on SSRF prevention.

URL safety standard:

- Allowed schemes are only `http` and `https`.
  Example allowed: `https://example.com/docs`
  Example blocked: `file:///etc/passwd`

- Hostnames must be present and must not include embedded credentials.
  Example allowed: `https://example.com/`
  Example blocked: `https://user:pass@example.com/`

- Localhost hostnames are blocked.
  Example blocked: `http://localhost:8000/`
  Example blocked: `http://app.localhost/`

- Literal private or local IP addresses are blocked.
  Example blocked: `http://127.0.0.1/`
  Example blocked: `http://192.168.1.1/`
  Example blocked: `http://169.254.169.254/`

- Before real fetching, hostnames should resolve only to public IP addresses.
  Example allowed: `example.com -> 93.184.216.34`
  Example blocked: `metadata.example -> 169.254.169.254`

- Redirects must remain on the same hostname, except root/www variants are
  treated as equivalent, and pass the same safety checks.
  Example allowed: `https://example.com/docs -> /about`
  Example allowed: `https://example.com/ -> https://www.example.com/`
  Example blocked: `https://example.com/docs -> http://127.0.0.1/admin`
"""

from dataclasses import dataclass
from ipaddress import ip_address
import socket
from urllib.parse import urljoin, urlparse

from app.services.url_utils import SUPPORTED_SCHEMES


MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}


class UnsafeUrlError(ValueError):
    """Raised when a URL is unsafe for server-side fetching."""


@dataclass(frozen=True)
class UrlSafetyPolicy:
    """Runtime limits that the fetcher should apply consistently."""

    max_redirects: int = MAX_REDIRECTS
    max_response_bytes: int = MAX_RESPONSE_BYTES


def assert_safe_url(
    url: str,
    *,
    allowed_hostname: str | None = None,
    resolve_host: bool = False,
) -> None:
    """Raise if a URL is unsafe for crawling.

    `resolve_host` is intended for the fetch layer, immediately before making
    a request. Scan creation can use the non-DNS checks so the form remains
    responsive even before the crawler performs network IO.
    """

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in SUPPORTED_SCHEMES:
        raise UnsafeUrlError("Only http and https URLs are supported.")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URLs with embedded credentials are not supported.")

    hostname = _normalized_hostname(parsed.hostname)
    if not hostname:
        raise UnsafeUrlError("Enter a valid website URL.")
    if allowed_hostname and not _hostnames_equivalent(hostname, allowed_hostname):
        raise UnsafeUrlError("Crawler redirects must stay on the same hostname.")

    _assert_safe_hostname(hostname)

    if resolve_host:
        assert_hostname_resolves_publicly(hostname)


def assert_hostname_resolves_publicly(hostname: str) -> None:
    """Resolve a hostname and reject private or otherwise unsafe IP targets."""

    normalized = _normalized_hostname(hostname)
    if not normalized:
        raise UnsafeUrlError("Enter a valid website URL.")

    try:
        addresses = socket.getaddrinfo(normalized, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError("Website hostname could not be resolved.") from exc

    if not addresses:
        raise UnsafeUrlError("Website hostname could not be resolved.")

    for address in addresses:
        ip_text = address[4][0]
        if _is_blocked_ip(ip_text):
            raise UnsafeUrlError("Website resolves to a blocked network address.")


def validate_redirect_url(source_url: str, redirect_url: str) -> str:
    """Return a safe absolute redirect URL or raise if the redirect is unsafe."""

    absolute_redirect = urljoin(source_url, redirect_url)
    source_hostname = _normalized_hostname(urlparse(source_url).hostname)
    assert_safe_url(
        absolute_redirect,
        allowed_hostname=source_hostname,
        resolve_host=True,
    )
    return absolute_redirect


def is_safe_url_for_scan(url: str) -> bool:
    """Boolean wrapper used by tests or lightweight callers."""

    try:
        assert_safe_url(url)
    except UnsafeUrlError:
        return False
    return True


def _assert_safe_hostname(hostname: str) -> None:
    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".localhost"):
        raise UnsafeUrlError("Localhost URLs are not allowed.")
    if _is_blocked_ip(hostname):
        raise UnsafeUrlError("Private or local network URLs are not allowed.")


def _is_blocked_ip(value: str) -> bool:
    try:
        parsed_ip = ip_address(value)
    except ValueError:
        return False

    return (
        parsed_ip.is_private
        or parsed_ip.is_loopback
        or parsed_ip.is_link_local
        or parsed_ip.is_multicast
        or parsed_ip.is_unspecified
        or parsed_ip.is_reserved
    )


def _normalized_hostname(hostname: str | None) -> str:
    if not hostname:
        return ""
    return hostname.rstrip(".").lower()


def _hostnames_equivalent(hostname: str, allowed_hostname: str) -> bool:
    normalized = _normalized_hostname(hostname)
    allowed = _normalized_hostname(allowed_hostname)
    if not normalized or not allowed:
        return False
    return _without_leading_www(normalized) == _without_leading_www(allowed)


def _without_leading_www(hostname: str) -> str:
    return hostname.removeprefix("www.")
