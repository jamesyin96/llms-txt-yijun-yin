import httpx

from app.services.fetcher import FetchConfig, FetchError, FetchResult
from app.services.robots import parse_robots_txt
from app.services.sitemap import (
    discover_sitemap_urls,
    fallback_sitemap_url,
    parse_sitemap_xml,
)
from app.services.url_utils import canonicalize_discovered_url, is_same_hostname


ROOT_URL = "https://example.com/"


def test_parse_urlset_extracts_and_deduplicates_urls() -> None:
    parsed = parse_sitemap_xml(
        """
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://example.com/a#section</loc></url>
          <url><loc>https://example.com/b?x=1</loc></url>
          <url><loc>https://example.com/a</loc></url>
        </urlset>
        """,
        base_url=ROOT_URL,
    )

    assert parsed.page_urls == (
        "https://example.com/a",
        "https://example.com/b?x=1",
    )
    assert parsed.sitemap_urls == ()


def test_parse_sitemapindex_extracts_nested_sitemaps() -> None:
    parsed = parse_sitemap_xml(
        """
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <sitemap><loc>/pages.xml</loc></sitemap>
          <sitemap><loc>https://example.com/blog.xml</loc></sitemap>
        </sitemapindex>
        """,
        base_url=ROOT_URL,
    )

    assert parsed.page_urls == ()
    assert parsed.sitemap_urls == (
        "https://example.com/pages.xml",
        "https://example.com/blog.xml",
    )


def test_parse_invalid_xml_returns_empty_result() -> None:
    parsed = parse_sitemap_xml("<not xml", base_url=ROOT_URL)

    assert parsed.page_urls == ()
    assert parsed.sitemap_urls == ()


def test_fallback_sitemap_url() -> None:
    assert fallback_sitemap_url(ROOT_URL) == "https://example.com/sitemap.xml"


def test_url_helpers_for_sitemap_filtering() -> None:
    assert canonicalize_discovered_url("/docs#intro", base_url=ROOT_URL) == "https://example.com/docs"
    assert is_same_hostname("https://example.com/docs", ROOT_URL)
    assert not is_same_hostname("https://other.example.com/docs", ROOT_URL)


def test_discovery_uses_robots_sitemap_before_fallback() -> None:
    robots = parse_robots_txt("Sitemap: /robots-sitemap.xml", root_url=ROOT_URL)
    calls: list[str] = []

    def fake_fetcher(
        url: str,
        *,
        config: FetchConfig | None = None,
        client: httpx.Client | None = None,
    ) -> FetchResult:
        calls.append(url)
        if url.endswith("robots-sitemap.xml"):
            body = "<urlset><url><loc>https://example.com/from-robots</loc></url></urlset>"
        else:
            body = "<urlset><url><loc>https://example.com/from-fallback</loc></url></urlset>"
        return _fetch_result(url, body)

    result = discover_sitemap_urls(ROOT_URL, robots, fetcher=fake_fetcher)

    assert calls == [
        "https://example.com/robots-sitemap.xml",
        "https://example.com/sitemap.xml",
    ]
    assert result.page_urls == (
        "https://example.com/from-robots",
        "https://example.com/from-fallback",
    )
    assert result.sitemap_urls_fetched == tuple(calls)


def test_discovery_fetches_nested_sitemap_index() -> None:
    robots = parse_robots_txt("", root_url=ROOT_URL)

    def fake_fetcher(
        url: str,
        *,
        config: FetchConfig | None = None,
        client: httpx.Client | None = None,
    ) -> FetchResult:
        if url.endswith("sitemap.xml"):
            body = "<sitemapindex><sitemap><loc>/nested.xml</loc></sitemap></sitemapindex>"
        else:
            body = "<urlset><url><loc>https://example.com/nested-page</loc></url></urlset>"
        return _fetch_result(url, body)

    result = discover_sitemap_urls(ROOT_URL, robots, fetcher=fake_fetcher)

    assert result.page_urls == ("https://example.com/nested-page",)
    assert result.sitemap_urls_fetched == (
        "https://example.com/sitemap.xml",
        "https://example.com/nested.xml",
    )


def test_discovery_filters_cross_host_and_robots_disallowed_urls() -> None:
    robots = parse_robots_txt(
        """
        User-agent: *
        Disallow: /private
        """,
        root_url=ROOT_URL,
    )

    def fake_fetcher(
        url: str,
        *,
        config: FetchConfig | None = None,
        client: httpx.Client | None = None,
    ) -> FetchResult:
        body = """
        <urlset>
          <url><loc>https://example.com/public</loc></url>
          <url><loc>https://example.com/private</loc></url>
          <url><loc>https://other.example.com/public</loc></url>
        </urlset>
        """
        return _fetch_result(url, body)

    result = discover_sitemap_urls(ROOT_URL, robots, fetcher=fake_fetcher)

    assert result.page_urls == ("https://example.com/public",)


def test_discovery_skips_fetch_errors_and_http_errors() -> None:
    robots = parse_robots_txt("Sitemap: /broken.xml", root_url=ROOT_URL)

    def fake_fetcher(
        url: str,
        *,
        config: FetchConfig | None = None,
        client: httpx.Client | None = None,
    ) -> FetchResult:
        if url.endswith("broken.xml"):
            raise FetchError("unavailable")
        return _fetch_result(url, "", status_code=404)

    result = discover_sitemap_urls(ROOT_URL, robots, fetcher=fake_fetcher)

    assert result.page_urls == ()
    assert result.sitemap_urls_fetched == ()


def test_discovery_works_with_real_fetcher_and_mock_transport() -> None:
    robots = parse_robots_txt("", root_url=ROOT_URL)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.com/sitemap.xml"
        return httpx.Response(
            200,
            content=b"<urlset><url><loc>https://example.com/page</loc></url></urlset>",
            request=request,
        )

    result = discover_sitemap_urls(
        ROOT_URL,
        robots,
        config=FetchConfig(resolve_host=False),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert result.page_urls == ("https://example.com/page",)


def _fetch_result(url: str, body: str, *, status_code: int = 200) -> FetchResult:
    return FetchResult(
        requested_url=url,
        final_url=url,
        status_code=status_code,
        content_type="application/xml",
        content=body.encode("utf-8"),
        redirect_count=0,
    )

