import pytest

from app.services.url_utils import normalize_root_url


def test_normalize_adds_https() -> None:
    assert normalize_root_url("example.com") == "https://example.com/"


def test_normalize_removes_query_and_fragment() -> None:
    assert normalize_root_url("https://example.com/docs?q=1#top") == "https://example.com/docs"


def test_normalize_rejects_unsupported_scheme() -> None:
    with pytest.raises(ValueError):
        normalize_root_url("file:///etc/passwd")

