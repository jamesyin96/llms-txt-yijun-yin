import httpx

from app.services.crawler import CrawlConfig, crawl_site
from app.services.fetcher import FetchConfig, FetchError, FetchResult
from app.services.resource_classifier import ResourceType


ROOT_URL = "https://example.com/"


def test_crawler_fetches_homepage_before_sitemap_urls_for_site_identity() -> None:
    calls: list[str] = []

    fetcher = _mapping_fetcher(
        {
            "https://example.com/robots.txt": (200, ""),
            "https://example.com/sitemap.xml": (
                200,
                "<urlset><url><loc>https://example.com/from-sitemap</loc></url></urlset>",
                "application/xml",
            ),
            "https://example.com/from-sitemap": (200, _html("Sitemap Page")),
            "https://example.com/": (200, _html("Home Page")),
        },
        calls=calls,
    )

    result = crawl_site(ROOT_URL, fetcher=fetcher)

    assert [resource.url for resource in result.resources] == [
        "https://example.com/",
        "https://example.com/from-sitemap",
    ]
    assert calls[:4] == [
        "https://example.com/robots.txt",
        "https://example.com/sitemap.xml",
        "https://example.com/",
        "https://example.com/from-sitemap",
    ]


def test_crawler_uses_homepage_when_sitemap_is_missing() -> None:
    fetcher = _mapping_fetcher(
        {
            "https://example.com/robots.txt": (404, ""),
            "https://example.com/sitemap.xml": (404, ""),
            "https://example.com/": (200, _html("Home Page")),
        }
    )

    result = crawl_site(ROOT_URL, fetcher=fetcher)

    assert [resource.url for resource in result.resources] == ["https://example.com/"]
    assert result.sitemap_urls_fetched == ()


def test_crawler_respects_depth_limit() -> None:
    fetcher = _mapping_fetcher(
        {
            "https://example.com/robots.txt": (404, ""),
            "https://example.com/sitemap.xml": (404, ""),
            "https://example.com/": (200, _html("Home", links=["/one"])),
            "https://example.com/one": (200, _html("One", links=["/two"])),
            "https://example.com/two": (200, _html("Two")),
        }
    )

    result = crawl_site(ROOT_URL, crawl_config=CrawlConfig(max_depth=1), fetcher=fetcher)

    assert [resource.url for resource in result.resources] == [
        "https://example.com/",
        "https://example.com/one",
    ]


def test_crawler_respects_max_pages_limit() -> None:
    fetcher = _mapping_fetcher(
        {
            "https://example.com/robots.txt": (404, ""),
            "https://example.com/sitemap.xml": (404, ""),
            "https://example.com/": (200, _html("Home", links=["/one", "/two", "/three"])),
            "https://example.com/one": (200, _html("One")),
            "https://example.com/two": (200, _html("Two")),
            "https://example.com/three": (200, _html("Three")),
        }
    )

    result = crawl_site(ROOT_URL, crawl_config=CrawlConfig(max_pages=2), fetcher=fetcher)

    assert len(result.resources) == 2
    assert [resource.url for resource in result.resources] == [
        "https://example.com/",
        "https://example.com/one",
    ]


def test_crawler_respects_duration_limit(monkeypatch) -> None:
    import app.services.crawler as crawler

    fetcher = _mapping_fetcher(
        {
            "https://example.com/robots.txt": (404, ""),
            "https://example.com/sitemap.xml": (404, ""),
        }
    )
    times = iter([0.0, 1.0])
    monkeypatch.setattr(crawler, "monotonic", lambda: next(times))

    result = crawler.crawl_site(
        ROOT_URL,
        crawl_config=CrawlConfig(max_duration_seconds=0.5),
        fetcher=fetcher,
    )

    assert result.resources == ()
    assert (
        "https://example.com/",
        "Crawl stopped after reaching the time budget.",
    ) in [(skipped.url, skipped.reason) for skipped in result.skipped]


def test_crawler_skips_robots_disallowed_urls() -> None:
    fetcher = _mapping_fetcher(
        {
            "https://example.com/robots.txt": (
                200,
                "User-agent: *\nDisallow: /private\n",
                "text/plain",
            ),
            "https://example.com/sitemap.xml": (404, ""),
            "https://example.com/": (200, _html("Home", links=["/private", "/public"])),
            "https://example.com/public": (200, _html("Public")),
        }
    )

    result = crawl_site(ROOT_URL, fetcher=fetcher)

    assert [resource.url for resource in result.resources] == [
        "https://example.com/",
        "https://example.com/public",
    ]
    assert ("https://example.com/private", "URL is disallowed by robots.txt.") in [
        (skipped.url, skipped.reason) for skipped in result.skipped
    ]


def test_crawler_includes_pdf_without_fetching_pdf() -> None:
    calls: list[str] = []
    fetcher = _mapping_fetcher(
        {
            "https://example.com/robots.txt": (404, ""),
            "https://example.com/sitemap.xml": (404, ""),
            "https://example.com/": (200, _html("Home", links=["/report.pdf"])),
        },
        calls=calls,
    )

    result = crawl_site(ROOT_URL, fetcher=fetcher)

    assert ("https://example.com/report.pdf", ResourceType.PDF) in [
        (resource.url, resource.resource_type) for resource in result.resources
    ]
    assert "https://example.com/report.pdf" not in calls


def test_crawler_includes_meaningful_images_and_skips_static_assets() -> None:
    fetcher = _mapping_fetcher(
        {
            "https://example.com/robots.txt": (404, ""),
            "https://example.com/sitemap.xml": (404, ""),
            "https://example.com/": (
                200,
                """
                <html>
                  <head><title>Home</title></head>
                  <body>
                    <a href="/app.css">Styles</a>
                    <img src="/media/chart.png" alt="Revenue chart" width="800" height="600">
                    <img src="/favicon.png" alt="Icon" width="400" height="400">
                  </body>
                </html>
                """,
            ),
        }
    )

    result = crawl_site(ROOT_URL, fetcher=fetcher)

    assert ("https://example.com/media/chart.png", ResourceType.IMAGE) in [
        (resource.url, resource.resource_type) for resource in result.resources
    ]
    assert ("https://example.com/app.css", "Static assets are skipped.") in [
        (skipped.url, skipped.reason) for skipped in result.skipped
    ]
    assert ("https://example.com/favicon.png", "Image URL looks decorative or icon-like.") in [
        (skipped.url, skipped.reason) for skipped in result.skipped
    ]


def test_crawler_records_fetch_errors_and_continues() -> None:
    def fetcher(
        url: str,
        *,
        config: FetchConfig | None = None,
        client: httpx.Client | None = None,
    ) -> FetchResult:
        if url.endswith("robots.txt") or url.endswith("sitemap.xml"):
            return _fetch_result(url, "", status_code=404)
        if url.endswith("/bad"):
            raise FetchError("bad page unavailable")
        if url.endswith("/good"):
            return _fetch_result(url, _html("Good"))
        return _fetch_result(url, _html("Home", links=["/bad", "/good"]))

    result = crawl_site(ROOT_URL, fetcher=fetcher)

    assert "https://example.com/good" in [resource.url for resource in result.resources]
    assert ("https://example.com/bad", "bad page unavailable") in [
        (error.url, error.error) for error in result.errors
    ]


def test_crawler_skips_non_html_fetch_response() -> None:
    fetcher = _mapping_fetcher(
        {
            "https://example.com/robots.txt": (404, ""),
            "https://example.com/sitemap.xml": (404, ""),
            "https://example.com/": (200, _html("Home", links=["/data"])),
            "https://example.com/data": (200, "{}", "application/json"),
        }
    )

    result = crawl_site(ROOT_URL, fetcher=fetcher)

    assert ("https://example.com/data", "Fetched resource is not HTML.") in [
        (skipped.url, skipped.reason) for skipped in result.skipped
    ]


def _mapping_fetcher(
    responses: dict[str, tuple[int, str] | tuple[int, str, str]],
    *,
    calls: list[str] | None = None,
):
    def fetcher(
        url: str,
        *,
        config: FetchConfig | None = None,
        client: httpx.Client | None = None,
    ) -> FetchResult:
        if calls is not None:
            calls.append(url)
        status_code, body, *content_type = responses[url]
        return _fetch_result(
            url,
            body,
            status_code=status_code,
            content_type=content_type[0] if content_type else "text/html",
        )

    return fetcher


def _fetch_result(
    url: str,
    body: str,
    *,
    status_code: int = 200,
    content_type: str = "text/html",
) -> FetchResult:
    return FetchResult(
        requested_url=url,
        final_url=url,
        status_code=status_code,
        content_type=content_type,
        content=body.encode("utf-8"),
        redirect_count=0,
    )


def _html(title: str, *, links: list[str] | None = None) -> str:
    anchors = "\n".join(f'<a href="{href}">{href}</a>' for href in links or [])
    return f"""
    <html>
      <head>
        <title>{title}</title>
        <meta name="description" content="{title} description">
      </head>
      <body>
        <h1>{title}</h1>
        {anchors}
      </body>
    </html>
    """
