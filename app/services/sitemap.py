"""Sitemap discovery and XML parsing.

Sitemaps are the first source of crawl URLs after robots.txt. This module parses
regular sitemap URL sets and sitemap indexes, fetches nested sitemaps through
the safe fetcher, filters to same-host URLs, deduplicates results, and applies
robots allow/disallow rules to discovered page URLs.
"""

from dataclasses import dataclass, field
from time import monotonic
from typing import Protocol
from xml.etree import ElementTree

import httpx

from app.services.fetcher import FetchConfig, FetchError, FetchResult, fetch_url
from app.services.robots import RobotsRules
from app.services.url_utils import canonicalize_discovered_url, is_same_hostname


DEFAULT_SITEMAP_PATH = "/sitemap.xml"
MAX_SITEMAP_DEPTH = 2
MAX_SITEMAPS_FETCHED = 10


@dataclass(frozen=True)
class ParsedSitemap:
    """URLs extracted from one sitemap XML document."""

    page_urls: tuple[str, ...] = field(default_factory=tuple)
    sitemap_urls: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SitemapDiscoveryResult:
    """Aggregated sitemap discovery result for a website."""

    page_urls: tuple[str, ...] = field(default_factory=tuple)
    sitemap_urls_fetched: tuple[str, ...] = field(default_factory=tuple)
    sitemap_limit_reached: bool = False
    page_url_limit_reached: bool = False
    duration_seconds: float = 0.0


class FetchSitemapFn(Protocol):
    """Callable shape for dependency-injected sitemap fetching."""

    def __call__(
        self,
        url: str,
        *,
        config: FetchConfig | None = None,
        client: httpx.Client | None = None,
    ) -> FetchResult:
        pass


def discover_sitemap_urls(
    root_url: str,
    robots_rules: RobotsRules,
    *,
    config: FetchConfig | None = None,
    client: httpx.Client | None = None,
    fetcher: FetchSitemapFn = fetch_url,
    max_depth: int = MAX_SITEMAP_DEPTH,
    max_sitemaps: int = MAX_SITEMAPS_FETCHED,
    max_page_urls: int | None = None,
) -> SitemapDiscoveryResult:
    """Discover crawlable same-host page URLs from robots and fallback sitemaps."""

    started_at = monotonic()
    seed_sitemaps = _sitemap_seeds(root_url, robots_rules)
    queue: list[tuple[str, int]] = [(sitemap_url, 0) for sitemap_url in seed_sitemaps]
    seen_sitemaps: set[str] = set()
    fetched_sitemaps: list[str] = []
    page_urls: list[str] = []
    seen_pages: set[str] = set()

    # Treat sitemaps as discovery hints, not a full-site inventory. Big sites
    # can expose huge sitemap indexes, while the crawler only needs enough page
    # candidates to fill the scan's max_pages budget.
    while queue and len(fetched_sitemaps) < max_sitemaps:
        sitemap_url, depth = queue.pop(0)
        if sitemap_url in seen_sitemaps or depth > max_depth:
            continue
        seen_sitemaps.add(sitemap_url)

        try:
            result = fetcher(sitemap_url, config=config, client=client)
        except FetchError:
            continue
        if result.status_code >= 400:
            continue

        fetched_sitemaps.append(sitemap_url)
        parsed = parse_sitemap_xml(result.text, base_url=result.final_url)

        for nested_sitemap in parsed.sitemap_urls:
            if nested_sitemap not in seen_sitemaps and is_same_hostname(nested_sitemap, root_url):
                queue.append((nested_sitemap, depth + 1))

        for page_url in parsed.page_urls:
            if (
                page_url not in seen_pages
                and is_same_hostname(page_url, root_url)
                and robots_rules.is_allowed(page_url)
            ):
                seen_pages.add(page_url)
                page_urls.append(page_url)
                if max_page_urls is not None and len(page_urls) >= max_page_urls:
                    break

        if max_page_urls is not None and len(page_urls) >= max_page_urls:
            break

    return SitemapDiscoveryResult(
        page_urls=tuple(page_urls),
        sitemap_urls_fetched=tuple(fetched_sitemaps),
        sitemap_limit_reached=bool(queue) and len(fetched_sitemaps) >= max_sitemaps,
        page_url_limit_reached=max_page_urls is not None and len(page_urls) >= max_page_urls,
        duration_seconds=round(monotonic() - started_at, 3),
    )


def parse_sitemap_xml(content: str, *, base_url: str) -> ParsedSitemap:
    """Parse a sitemap XML document and return page and nested sitemap URLs."""

    try:
        root = ElementTree.fromstring(content.encode("utf-8"))
    except ElementTree.ParseError:
        return ParsedSitemap()

    root_name = _local_name(root.tag)
    if root_name == "urlset":
        return ParsedSitemap(page_urls=_extract_locs(root, base_url=base_url))
    if root_name == "sitemapindex":
        return ParsedSitemap(sitemap_urls=_extract_locs(root, base_url=base_url))
    return ParsedSitemap()


def fallback_sitemap_url(root_url: str) -> str:
    """Return the conventional `/sitemap.xml` URL for a root URL."""

    return canonicalize_discovered_url(DEFAULT_SITEMAP_PATH, base_url=root_url)


def _sitemap_seeds(root_url: str, robots_rules: RobotsRules) -> tuple[str, ...]:
    seeds = [url for url in robots_rules.sitemap_urls if is_same_hostname(url, root_url)]
    seeds.append(fallback_sitemap_url(root_url))
    return tuple(dict.fromkeys(seeds))


def _extract_locs(element: ElementTree.Element, *, base_url: str) -> tuple[str, ...]:
    urls: list[str] = []
    for loc in element.iter():
        if _local_name(loc.tag) != "loc" or not loc.text:
            continue
        try:
            urls.append(canonicalize_discovered_url(loc.text, base_url=base_url))
        except ValueError:
            continue
    return tuple(dict.fromkeys(urls))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()
