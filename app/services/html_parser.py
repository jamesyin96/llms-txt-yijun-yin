"""HTML metadata, link, and image extraction.

This module parses already-fetched HTML. It does not perform network requests
and does not write to the database. The crawler will call it after `fetcher.py`
returns an HTML response.
"""

from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from app.services.url_utils import canonicalize_discovered_url, is_same_hostname


@dataclass(frozen=True)
class LinkCandidate:
    """A same-host URL discovered from an anchor tag."""

    url: str
    text: str
    source_url: str


@dataclass(frozen=True)
class ImageCandidate:
    """A same-host image URL discovered from an image tag."""

    url: str
    alt: str
    title: str
    width: int | None
    height: int | None
    source_url: str


@dataclass(frozen=True)
class HtmlParseResult:
    """Parsed HTML metadata and same-host resource candidates."""

    page_url: str
    title: str
    description: str
    canonical_url: str | None
    h1: str
    headings: tuple[str, ...] = field(default_factory=tuple)
    links: tuple[LinkCandidate, ...] = field(default_factory=tuple)
    images: tuple[ImageCandidate, ...] = field(default_factory=tuple)


def parse_html_document(html: str, *, page_url: str, root_url: str) -> HtmlParseResult:
    """Parse HTML into metadata, internal links, and image candidates."""

    soup = BeautifulSoup(html, "html.parser")

    return HtmlParseResult(
        page_url=page_url,
        title=_extract_title(soup),
        description=_extract_description(soup),
        canonical_url=_extract_canonical_url(soup, page_url=page_url, root_url=root_url),
        h1=_first_heading_text(soup, "h1"),
        headings=_extract_headings(soup),
        links=_extract_links(soup, page_url=page_url, root_url=root_url),
        images=_extract_images(soup, page_url=page_url, root_url=root_url),
    )


def _extract_title(soup: BeautifulSoup) -> str:
    title = _clean_text(soup.title.get_text(" ")) if soup.title else ""
    return title or _meta_content(soup, property_name="og:title")


def _extract_description(soup: BeautifulSoup) -> str:
    return (
        _meta_content(soup, name="description")
        or _meta_content(soup, property_name="og:description")
        or _meta_content(soup, name="twitter:description")
    )


def _extract_canonical_url(soup: BeautifulSoup, *, page_url: str, root_url: str) -> str | None:
    canonical = soup.find("link", rel=lambda value: value and "canonical" in _rel_values(value))
    if not isinstance(canonical, Tag):
        return None

    href = canonical.get("href")
    if not href:
        return None

    try:
        canonical_url = canonicalize_discovered_url(str(href), base_url=page_url)
    except ValueError:
        return None

    if not is_same_hostname(canonical_url, root_url):
        return None
    return canonical_url


def _extract_headings(soup: BeautifulSoup) -> tuple[str, ...]:
    headings: list[str] = []
    seen: set[str] = set()

    for heading in soup.find_all(["h1", "h2", "h3"]):
        text = _clean_text(heading.get_text(" "))
        if text and text not in seen:
            seen.add(text)
            headings.append(text)

    return tuple(headings)


def _first_heading_text(soup: BeautifulSoup, tag_name: str) -> str:
    heading = soup.find(tag_name)
    if not isinstance(heading, Tag):
        return ""
    return _clean_text(heading.get_text(" "))


def _extract_links(soup: BeautifulSoup, *, page_url: str, root_url: str) -> tuple[LinkCandidate, ...]:
    links_by_url: dict[str, LinkCandidate] = {}

    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue

        try:
            url = canonicalize_discovered_url(str(anchor["href"]), base_url=page_url)
        except ValueError:
            continue

        if not is_same_hostname(url, root_url):
            continue

        text = _link_text(anchor)
        existing = links_by_url.get(url)
        if existing is None or (not existing.text and text):
            links_by_url[url] = LinkCandidate(url=url, text=text, source_url=page_url)

    return tuple(links_by_url.values())


def _extract_images(
    soup: BeautifulSoup,
    *,
    page_url: str,
    root_url: str,
) -> tuple[ImageCandidate, ...]:
    images_by_url: dict[str, ImageCandidate] = {}

    for image in soup.find_all("img", src=True):
        if not isinstance(image, Tag):
            continue

        try:
            url = canonicalize_discovered_url(str(image["src"]), base_url=page_url)
        except ValueError:
            continue

        if not is_same_hostname(url, root_url):
            continue

        candidate = ImageCandidate(
            url=url,
            alt=_clean_text(str(image.get("alt", ""))),
            title=_clean_text(str(image.get("title", ""))),
            width=_parse_dimension(image.get("width")),
            height=_parse_dimension(image.get("height")),
            source_url=page_url,
        )
        existing = images_by_url.get(url)
        if existing is None or (not existing.alt and candidate.alt):
            images_by_url[url] = candidate

    return tuple(images_by_url.values())


def _link_text(anchor: Tag) -> str:
    return (
        _clean_text(anchor.get_text(" "))
        or _clean_text(str(anchor.get("aria-label", "")))
        or _clean_text(str(anchor.get("title", "")))
        or _first_image_alt(anchor)
    )


def _first_image_alt(anchor: Tag) -> str:
    image = anchor.find("img")
    if not isinstance(image, Tag):
        return ""
    return _clean_text(str(image.get("alt", "")))


def _meta_content(
    soup: BeautifulSoup,
    *,
    name: str | None = None,
    property_name: str | None = None,
) -> str:
    attrs = {"name": name} if name else {"property": property_name}
    meta = soup.find("meta", attrs=attrs)
    if not isinstance(meta, Tag):
        return ""
    return _clean_text(str(meta.get("content", "")))


def _rel_values(value: object) -> set[str]:
    if isinstance(value, list):
        return {str(item).lower() for item in value}
    return {item.lower() for item in str(value).split()}


def _parse_dimension(value: object) -> int | None:
    if value is None:
        return None
    try:
        dimension = int(str(value).strip())
    except ValueError:
        return None
    return dimension if dimension >= 0 else None


def _clean_text(value: str) -> str:
    return " ".join(value.split())

