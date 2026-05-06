"""URL normalization and comparison helpers.

This module handles user-facing URL cleanup. SSRF protection lives in
`app.services.security` so normalization and fetch safety can be tested and
evolved independently.
"""

from urllib.parse import urljoin, urlparse, urlunparse


SUPPORTED_SCHEMES = {"http", "https"}


def normalize_root_url(raw_url: str) -> str:
    """Normalize a user-submitted website URL for scan creation.

    Examples:
    - `example.com` becomes `https://example.com/`
    - query strings and fragments are removed
    - unsupported schemes are rejected
    """

    value = raw_url.strip()
    if not value:
        raise ValueError("Enter a website URL.")

    if "://" not in value:
        value = f"https://{value}"

    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if scheme not in SUPPORTED_SCHEMES:
        raise ValueError("Only http and https URLs are supported.")
    if not parsed.netloc:
        raise ValueError("Enter a valid website URL.")

    netloc = parsed.netloc.lower()
    path = parsed.path or "/"

    return urlunparse((scheme, netloc, path, "", "", ""))


def canonicalize_discovered_url(raw_url: str, *, base_url: str) -> str:
    """Resolve and normalize a URL discovered while crawling."""

    absolute_url = urljoin(base_url, raw_url.strip())
    parsed = urlparse(absolute_url)
    scheme = parsed.scheme.lower()
    if scheme not in SUPPORTED_SCHEMES or not parsed.netloc:
        raise ValueError("Only absolute http and https URLs are supported.")

    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def is_same_hostname(url: str, root_url: str) -> bool:
    """Return whether `url` has the same hostname as `root_url`."""

    url_host = urlparse(url).hostname
    root_host = urlparse(root_url).hostname
    if not url_host or not root_host:
        return False
    return url_host.rstrip(".").lower() == root_host.rstrip(".").lower()
