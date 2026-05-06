import httpx

from app.services.fetcher import FetchConfig, FetchError, FetchResult
from app.services.robots import fetch_robots_rules, parse_robots_txt, robots_url_for


ROOT_URL = "https://example.com/"


def test_robots_url_for_root_url() -> None:
    assert robots_url_for(ROOT_URL) == "https://example.com/robots.txt"
    assert robots_url_for("https://example.com/docs") == "https://example.com/robots.txt"


def test_missing_robots_allows_crawling() -> None:
    rules = parse_robots_txt("", root_url=ROOT_URL)

    assert rules.is_allowed("https://example.com/private")


def test_disallow_path_blocks_crawl() -> None:
    rules = parse_robots_txt(
        """
        User-agent: *
        Disallow: /private
        """,
        root_url=ROOT_URL,
    )

    assert not rules.is_allowed("https://example.com/private/page")
    assert rules.is_allowed("https://example.com/public/page")


def test_allow_longer_rule_overrides_disallow() -> None:
    rules = parse_robots_txt(
        """
        User-agent: *
        Disallow: /docs
        Allow: /docs/public
        """,
        root_url=ROOT_URL,
    )

    assert rules.is_allowed("https://example.com/docs/public/guide")
    assert not rules.is_allowed("https://example.com/docs/private")


def test_specific_user_agent_overrides_wildcard_group() -> None:
    rules = parse_robots_txt(
        """
        User-agent: *
        Disallow: /

        User-agent: llms-txt-generator
        Allow: /
        """,
        root_url=ROOT_URL,
    )

    assert rules.is_allowed("https://example.com/anything")
    assert not rules.is_allowed("https://example.com/anything", user_agent="other-crawler")


def test_extracts_and_deduplicates_sitemap_urls() -> None:
    rules = parse_robots_txt(
        """
        Sitemap: /sitemap.xml
        Sitemap: https://example.com/news-sitemap.xml
        Sitemap: /sitemap.xml
        """,
        root_url=ROOT_URL,
    )

    assert rules.sitemap_urls == (
        "https://example.com/sitemap.xml",
        "https://example.com/news-sitemap.xml",
    )


def test_empty_disallow_allows_everything() -> None:
    rules = parse_robots_txt(
        """
        User-agent: *
        Disallow:
        """,
        root_url=ROOT_URL,
    )

    assert rules.is_allowed("https://example.com/anything")


def test_supports_simple_wildcard_and_end_anchor_matching() -> None:
    rules = parse_robots_txt(
        """
        User-agent: *
        Disallow: /tmp/*.pdf$
        """,
        root_url=ROOT_URL,
    )

    assert not rules.is_allowed("https://example.com/tmp/report.pdf")
    assert rules.is_allowed("https://example.com/tmp/report.pdf?download=1")
    assert rules.is_allowed("https://example.com/tmp/report.html")


def test_fetch_robots_uses_fetcher_and_parses_result() -> None:
    calls: list[tuple[str, FetchConfig | None, httpx.Client | None]] = []

    def fake_fetcher(
        url: str,
        *,
        config: FetchConfig | None = None,
        client: httpx.Client | None = None,
    ) -> FetchResult:
        calls.append((url, config, client))
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/plain",
            content=b"User-agent: *\nDisallow: /blocked\nSitemap: /sitemap.xml\n",
            redirect_count=0,
        )

    config = FetchConfig(resolve_host=False)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    rules = fetch_robots_rules(ROOT_URL, config=config, client=client, fetcher=fake_fetcher)

    assert calls == [("https://example.com/robots.txt", config, client)]
    assert not rules.is_allowed("https://example.com/blocked")
    assert rules.sitemap_urls == ("https://example.com/sitemap.xml",)


def test_fetch_robots_allows_when_missing() -> None:
    def fake_fetcher(
        url: str,
        *,
        config: FetchConfig | None = None,
        client: httpx.Client | None = None,
    ) -> FetchResult:
        return FetchResult(
            requested_url=url,
            final_url=url,
            status_code=404,
            content_type="text/plain",
            content=b"",
            redirect_count=0,
        )

    rules = fetch_robots_rules(ROOT_URL, fetcher=fake_fetcher)

    assert rules.is_allowed("https://example.com/anything")
    assert rules.sitemap_urls == ()


def test_fetch_robots_allows_when_fetch_fails() -> None:
    def fake_fetcher(
        url: str,
        *,
        config: FetchConfig | None = None,
        client: httpx.Client | None = None,
    ) -> FetchResult:
        raise FetchError("network unavailable")

    rules = fetch_robots_rules(ROOT_URL, fetcher=fake_fetcher)

    assert rules.is_allowed("https://example.com/anything")


def test_fetch_robots_works_with_real_fetcher_and_mock_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.com/robots.txt"
        return httpx.Response(
            200,
            content=b"User-agent: *\nDisallow: /private\n",
            request=request,
        )

    rules = fetch_robots_rules(
        ROOT_URL,
        config=FetchConfig(resolve_host=False),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert not rules.is_allowed("https://example.com/private")
