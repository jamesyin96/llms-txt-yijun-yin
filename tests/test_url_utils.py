import pytest

from app.services.url_utils import is_same_hostname, normalize_root_url


def test_normalize_adds_https() -> None:
    assert normalize_root_url("example.com") == "https://example.com/"


def test_normalize_removes_query_and_fragment() -> None:
    assert normalize_root_url("https://example.com/docs?q=1#top") == "https://example.com/docs"


def test_normalize_rejects_unsupported_scheme() -> None:
    with pytest.raises(ValueError):
        normalize_root_url("file:///etc/passwd")


def test_same_hostname_allows_root_and_www_variants() -> None:
    assert is_same_hostname("https://www.example.com/about", "https://example.com/")
    assert is_same_hostname("https://example.com/about", "https://www.example.com/")


def test_same_hostname_blocks_unrelated_subdomains() -> None:
    assert not is_same_hostname("https://docs.example.com/", "https://example.com/")
