"""Crawler orchestration.

This module composes the safe fetcher, robots parser, sitemap discovery, HTML
parser, and resource classifier. It returns plain dataclasses so persistence and
formatting can evolve separately.
"""

from dataclasses import dataclass, field
from hashlib import sha256
from time import monotonic
from typing import Protocol

import httpx

from app.services.fetcher import FetchConfig, FetchError, FetchResult, fetch_url
from app.services.html_parser import HtmlParseResult, ImageCandidate, parse_html_document
from app.services.resource_classifier import (
    ResourceClassification,
    ResourceType,
    classify_image_candidate,
    classify_url,
)
from app.services.robots import fetch_robots_rules
from app.services.security import UnsafeUrlError
from app.services.sitemap import discover_sitemap_urls
from app.services.url_utils import is_same_hostname, normalize_root_url


@dataclass(frozen=True)
class CrawlConfig:
    """Crawl limits for V1."""

    max_pages: int = 100
    max_depth: int = 2
    max_duration_seconds: float = 30.0


@dataclass(frozen=True)
class CrawlResource:
    """A crawled or included resource that can feed ranking/formatting later."""

    url: str
    resource_type: ResourceType
    source_url: str | None = None
    link_text: str = ""
    title: str = ""
    description: str = ""
    canonical_url: str | None = None
    h1: str = ""
    headings: tuple[str, ...] = field(default_factory=tuple)
    status_code: int | None = None
    content_hash: str | None = None


@dataclass(frozen=True)
class SkippedUrl:
    """A discovered URL skipped by rules, limits, or classification."""

    url: str
    reason: str
    source_url: str | None = None


@dataclass(frozen=True)
class CrawlError:
    """A fetch or parse problem that should not fail the whole crawl."""

    url: str
    error: str
    source_url: str | None = None


@dataclass(frozen=True)
class CrawlResult:
    """Aggregated crawl output."""

    root_url: str
    resources: tuple[CrawlResource, ...] = field(default_factory=tuple)
    skipped: tuple[SkippedUrl, ...] = field(default_factory=tuple)
    errors: tuple[CrawlError, ...] = field(default_factory=tuple)
    sitemap_urls_fetched: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class _QueueItem:
    url: str
    depth: int
    source_url: str | None = None
    link_text: str = ""


class FetchCrawlerFn(Protocol):
    """Callable shape for dependency-injected crawler fetching."""

    def __call__(
        self,
        url: str,
        *,
        config: FetchConfig | None = None,
        client: httpx.Client | None = None,
    ) -> FetchResult:
        pass


def crawl_site(
    root_url: str,
    *,
    crawl_config: CrawlConfig | None = None,
    fetch_config: FetchConfig | None = None,
    client: httpx.Client | None = None,
    fetcher: FetchCrawlerFn = fetch_url,
) -> CrawlResult:
    """Crawl a site using sitemap-first discovery and homepage fallback."""

    normalized_root_url = normalize_root_url(root_url)
    config = crawl_config or CrawlConfig()

    robots_rules = fetch_robots_rules(
        normalized_root_url,
        config=fetch_config,
        client=client,
        fetcher=fetcher,
    )
    sitemap_result = discover_sitemap_urls(
        normalized_root_url,
        robots_rules,
        config=fetch_config,
        client=client,
        fetcher=fetcher,
    )

    queue: list[_QueueItem] = []
    queued_urls: set[str] = set()
    seen_urls: set[str] = set()
    resource_urls: set[str] = set()
    resources: list[CrawlResource] = []
    skipped: list[SkippedUrl] = []
    errors: list[CrawlError] = []
    started_at = monotonic()

    _enqueue(queue, queued_urls, _QueueItem(normalized_root_url, depth=0, source_url=None))
    for sitemap_url in sitemap_result.page_urls:
        _enqueue(queue, queued_urls, _QueueItem(sitemap_url, depth=0, source_url="sitemap"))

    while queue and len(resources) < config.max_pages:
        if _crawl_deadline_exceeded(started_at, config.max_duration_seconds):
            skipped.append(
                SkippedUrl(
                    normalized_root_url,
                    "Crawl stopped after reaching the time budget.",
                    None,
                )
            )
            break

        item = queue.pop(0)
        if item.url in seen_urls:
            continue
        seen_urls.add(item.url)

        classification = classify_url(item.url)
        if _should_skip_url(item, normalized_root_url, robots_rules, classification, skipped):
            continue

        if classification.resource_type is ResourceType.PDF:
            _add_resource(
                resources,
                resource_urls,
                CrawlResource(
                    url=item.url,
                    resource_type=ResourceType.PDF,
                    source_url=item.source_url,
                    link_text=item.link_text,
                ),
                max_pages=config.max_pages,
            )
            continue

        if classification.resource_type is ResourceType.IMAGE:
            skipped.append(SkippedUrl(item.url, classification.reason, item.source_url))
            continue

        try:
            fetched = fetcher(item.url, config=fetch_config, client=client)
        except (FetchError, UnsafeUrlError) as exc:
            errors.append(CrawlError(item.url, str(exc), item.source_url))
            continue

        if fetched.status_code >= 400:
            errors.append(CrawlError(item.url, f"HTTP {fetched.status_code}", item.source_url))
            continue
        if not _looks_like_html(fetched.content_type):
            skipped.append(SkippedUrl(item.url, "Fetched resource is not HTML.", item.source_url))
            continue

        parsed = parse_html_document(
            fetched.text,
            page_url=fetched.final_url,
            root_url=normalized_root_url,
        )
        _add_resource(
            resources,
            resource_urls,
            _html_resource(item, fetched, parsed),
            max_pages=config.max_pages,
        )

        _include_images(
            parsed.images,
            resources,
            resource_urls,
            skipped,
            max_pages=config.max_pages,
        )

        if item.depth >= config.max_depth:
            continue

        for link in parsed.links:
            _enqueue(
                queue,
                queued_urls,
                _QueueItem(
                    url=link.url,
                    depth=item.depth + 1,
                    source_url=item.url,
                    link_text=link.text,
                ),
            )

    return CrawlResult(
        root_url=normalized_root_url,
        resources=tuple(resources),
        skipped=tuple(skipped),
        errors=tuple(errors),
        sitemap_urls_fetched=sitemap_result.sitemap_urls_fetched,
    )


def _should_skip_url(
    item: _QueueItem,
    root_url: str,
    robots_rules,
    classification: ResourceClassification,
    skipped: list[SkippedUrl],
) -> bool:
    if not is_same_hostname(item.url, root_url):
        skipped.append(SkippedUrl(item.url, "URL is outside the root hostname.", item.source_url))
        return True
    if not robots_rules.is_allowed(item.url):
        skipped.append(SkippedUrl(item.url, "URL is disallowed by robots.txt.", item.source_url))
        return True
    if not classification.include:
        skipped.append(SkippedUrl(item.url, classification.reason, item.source_url))
        return True
    return False


def _html_resource(
    item: _QueueItem,
    fetched: FetchResult,
    parsed: HtmlParseResult,
) -> CrawlResource:
    return CrawlResource(
        url=fetched.final_url,
        resource_type=ResourceType.HTML,
        source_url=item.source_url,
        link_text=item.link_text,
        title=parsed.title,
        description=parsed.description,
        canonical_url=parsed.canonical_url,
        h1=parsed.h1,
        headings=parsed.headings,
        status_code=fetched.status_code,
        content_hash=_content_hash(fetched.content),
    )


def _include_images(
    images: tuple[ImageCandidate, ...],
    resources: list[CrawlResource],
    resource_urls: set[str],
    skipped: list[SkippedUrl],
    *,
    max_pages: int,
) -> None:
    for image in images:
        classification = classify_image_candidate(image)
        if not classification.include:
            skipped.append(SkippedUrl(image.url, classification.reason, image.source_url))
            continue

        _add_resource(
            resources,
            resource_urls,
            CrawlResource(
                url=image.url,
                resource_type=ResourceType.IMAGE,
                source_url=image.source_url,
                description=image.alt or image.title,
            ),
            max_pages=max_pages,
        )


def _add_resource(
    resources: list[CrawlResource],
    resource_urls: set[str],
    resource: CrawlResource,
    *,
    max_pages: int,
) -> None:
    if resource.url in resource_urls or len(resources) >= max_pages:
        return
    resource_urls.add(resource.url)
    resources.append(resource)


def _enqueue(queue: list[_QueueItem], queued_urls: set[str], item: _QueueItem) -> None:
    if item.url in queued_urls:
        return
    queued_urls.add(item.url)
    queue.append(item)


def _looks_like_html(content_type: str) -> bool:
    if not content_type:
        return True
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type in {"text/html", "application/xhtml+xml"}


def _content_hash(content: bytes) -> str:
    return sha256(content).hexdigest()


def _crawl_deadline_exceeded(started_at: float, max_duration_seconds: float) -> bool:
    return max_duration_seconds > 0 and monotonic() - started_at >= max_duration_seconds
