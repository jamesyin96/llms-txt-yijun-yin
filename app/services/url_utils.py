"""URL normalization helpers.

This module handles user-facing URL cleanup. SSRF protection lives in
`app.services.security` so normalization and fetch safety can be tested and
evolved independently.
"""

from urllib.parse import urlparse, urlunparse


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
