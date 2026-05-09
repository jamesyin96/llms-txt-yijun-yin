from unittest.mock import patch

import pytest

from app.services.security import (
    UnsafeUrlError,
    assert_hostname_resolves_publicly,
    assert_safe_url,
    is_safe_url_for_scan,
    validate_redirect_url,
)


def test_safe_public_https_url_is_allowed() -> None:
    assert_safe_url("https://example.com/")
    assert is_safe_url_for_scan("https://example.com/")


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://localhost.localdomain/",
        "http://app.localhost/",
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/",
        "http://[::1]/",
        "http://0.0.0.0/",
    ],
)
def test_blocks_localhost_and_private_network_urls(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        assert_safe_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "data:text/plain,hello",
        "javascript:alert(1)",
    ],
)
def test_blocks_unsafe_schemes(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        assert_safe_url(url)


def test_blocks_urls_with_embedded_credentials() -> None:
    with pytest.raises(UnsafeUrlError):
        assert_safe_url("https://user:pass@example.com/")


def test_blocks_cross_hostname_redirects() -> None:
    with pytest.raises(UnsafeUrlError):
        validate_redirect_url("https://example.com/docs", "https://evil.example.net/")


def test_allows_same_hostname_redirects() -> None:
    with patch("app.services.security.assert_hostname_resolves_publicly"):
        redirected = validate_redirect_url("https://example.com/docs", "/about")

    assert redirected == "https://example.com/about"


@pytest.mark.parametrize(
    ("source_url", "redirect_url", "expected"),
    [
        ("https://example.com/", "https://www.example.com/", "https://www.example.com/"),
        ("https://www.example.com/", "https://example.com/", "https://example.com/"),
    ],
)
def test_allows_root_and_www_redirect_variants(
    source_url: str,
    redirect_url: str,
    expected: str,
) -> None:
    with patch("app.services.security.assert_hostname_resolves_publicly"):
        redirected = validate_redirect_url(source_url, redirect_url)

    assert redirected == expected


def test_blocks_unrelated_subdomain_redirects() -> None:
    with pytest.raises(UnsafeUrlError):
        validate_redirect_url("https://example.com/", "https://docs.example.com/")


def test_blocks_dns_resolution_to_private_address() -> None:
    fake_addr = (socket_family_placeholder(), None, None, "", ("127.0.0.1", 0))
    with patch("socket.getaddrinfo", return_value=[fake_addr]):
        with pytest.raises(UnsafeUrlError):
            assert_hostname_resolves_publicly("example.com")


def test_allows_dns_resolution_to_public_address() -> None:
    fake_addr = (socket_family_placeholder(), None, None, "", ("8.8.8.8", 0))
    with patch("socket.getaddrinfo", return_value=[fake_addr]):
        assert_hostname_resolves_publicly("example.com")


def socket_family_placeholder() -> int:
    return 0
