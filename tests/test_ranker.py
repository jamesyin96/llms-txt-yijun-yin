from app.services.crawler import CrawlResource
from app.services.ranker import rank_resource, rank_resources
from app.services.resource_classifier import ResourceType


ROOT_URL = "https://example.com/"


def test_homepage_is_included_and_ranked_as_key_page() -> None:
    ranked = rank_resource(
        CrawlResource(url=ROOT_URL, resource_type=ResourceType.HTML),
        ROOT_URL,
    )

    assert ranked.include is True
    assert ranked.section == "Key Pages"
    assert ranked.score >= 100


def test_docs_and_guides_outrank_articles_and_legal_pages() -> None:
    resources = (
        CrawlResource(url=ROOT_URL, resource_type=ResourceType.HTML, title="Home"),
        CrawlResource(url="https://example.com/docs/api", resource_type=ResourceType.HTML, title="API Docs"),
        CrawlResource(url="https://example.com/guides/start", resource_type=ResourceType.HTML, title="Start Guide"),
        CrawlResource(url="https://example.com/blog/update", resource_type=ResourceType.HTML, title="Update"),
        CrawlResource(url="https://example.com/privacy", resource_type=ResourceType.HTML, title="Privacy Policy"),
    )

    ranked = rank_resources(resources, ROOT_URL)

    assert [resource.resource.url for resource in ranked] == [
        ROOT_URL,
        "https://example.com/docs/api",
        "https://example.com/guides/start",
        "https://example.com/blog/update",
    ]
    assert "https://example.com/privacy" not in [resource.resource.url for resource in ranked]


def test_low_value_urls_are_excluded() -> None:
    for url in (
        "https://example.com/login",
        "https://example.com/search?q=docs",
        "https://example.com/cart",
        "https://example.com/blog/tag/python",
    ):
        ranked = rank_resource(
            CrawlResource(url=url, resource_type=ResourceType.HTML, title="Low Value"),
            ROOT_URL,
        )

        assert ranked.include is False


def test_site_wide_metadata_does_not_override_path_section() -> None:
    ranked = rank_resource(
        CrawlResource(
            url="https://example.com/weblog/security-release",
            resource_type=ResourceType.HTML,
            title="Security release",
            description="Site navigation: API documentation, learn, RSS",
        ),
        ROOT_URL,
    )

    assert ranked.include is True
    assert ranked.section == "Articles"


def test_pdf_with_meaningful_name_is_included_as_document() -> None:
    ranked = rank_resource(
        CrawlResource(
            url="https://example.com/reports/annual-report.pdf",
            resource_type=ResourceType.PDF,
            link_text="Annual Report",
        ),
        ROOT_URL,
    )

    assert ranked.include is True
    assert ranked.section == "Documents"


def test_meaningful_image_is_included_but_scores_below_documentation() -> None:
    image = rank_resource(
        CrawlResource(
            url="https://example.com/images/chart.png",
            resource_type=ResourceType.IMAGE,
            description="Revenue chart",
        ),
        ROOT_URL,
    )
    docs = rank_resource(
        CrawlResource(
            url="https://example.com/docs/overview",
            resource_type=ResourceType.HTML,
            title="Overview",
        ),
        ROOT_URL,
    )

    assert image.include is True
    assert image.section == "Images"
    assert image.score < docs.score


def test_rank_resources_applies_max_resource_cap() -> None:
    resources = tuple(
        CrawlResource(
            url=f"https://example.com/docs/page-{index}",
            resource_type=ResourceType.HTML,
            title=f"Page {index}",
        )
        for index in range(5)
    )

    ranked = rank_resources(resources, ROOT_URL, max_resources=2)

    assert len(ranked) == 2
