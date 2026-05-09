"""Heuristic ranking and section assignment for crawled resources.

The crawler's job is discovery. This module decides which discovered resources
are likely useful in llms.txt, how important they are, and where they belong.
The rules are intentionally transparent so manual testing can tune them.
"""

from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlparse

from app.services.crawler import CrawlResource
from app.services.resource_classifier import ResourceType
from app.services.url_utils import normalize_root_url


MAX_INCLUDED_RESOURCES = 100
INCLUDE_THRESHOLD = 35.0

SECTION_PRIORITY = {
    "Key Pages": 0,
    "Products or Services": 1,
    "Documentation": 2,
    "Guides": 3,
    "Articles": 4,
    "Company": 5,
    "Support": 6,
    "Documents": 7,
    "Images": 8,
    "Optional": 9,
}

SECTION_KEYWORDS = (
    ("Documentation", ("docs", "documentation", "reference", "api", "developer", "developers")),
    ("Guides", ("guide", "guides", "tutorial", "tutorials", "learn", "getting-started", "quickstart")),
    ("Products or Services", ("product", "products", "features", "solutions", "pricing", "plans")),
    ("Articles", ("blog", "weblog", "news", "article", "articles", "changelog", "updates")),
    ("Company", ("about", "company", "team", "careers", "jobs")),
    ("Support", ("support", "help", "contact", "faq", "faqs", "community")),
)

LOW_VALUE_KEYWORDS = {
    "account",
    "admin",
    "archive",
    "auth",
    "billing",
    "cart",
    "category",
    "checkout",
    "cookie",
    "dashboard",
    "embed",
    "feed",
    "legal",
    "login",
    "logout",
    "payment",
    "privacy",
    "print",
    "rss",
    "search",
    "share",
    "signin",
    "signup",
    "tag",
    "terms",
}


@dataclass(frozen=True)
class RankedResource:
    """A resource annotated with ranking decisions for persistence/output."""

    resource: CrawlResource
    score: float
    section: str
    include: bool
    reason: str


def rank_resources(
    resources: tuple[CrawlResource, ...],
    root_url: str,
    *,
    max_resources: int = MAX_INCLUDED_RESOURCES,
) -> list[RankedResource]:
    """Rank crawl resources and return included resources in display order."""

    ranked = [rank_resource(resource, root_url) for resource in resources]
    included = [resource for resource in ranked if resource.include]
    included.sort(key=_rank_sort_key)
    return included[:max_resources]


def rank_resource(resource: CrawlResource, root_url: str) -> RankedResource:
    """Score one resource and assign its llms.txt section."""

    normalized_root_url = normalize_root_url(root_url)
    metadata_tokens = _metadata_tokens(resource)
    path_tokens = _path_tokens(resource.url)
    is_homepage = _is_homepage(resource.url, normalized_root_url)
    section = _section_for(resource, path_tokens, metadata_tokens, is_homepage)
    score = _base_score(resource.resource_type, is_homepage)
    reasons = [_base_reason(resource.resource_type, is_homepage)]

    positive_boost = _positive_keyword_boost(section, resource.resource_type, is_homepage)
    if positive_boost:
        score += positive_boost
        reasons.append(f"{section} signal")

    metadata_boost = _metadata_boost(resource)
    if metadata_boost:
        score += metadata_boost
        reasons.append("metadata")

    penalty = _low_value_penalty(path_tokens, resource.url)
    if penalty:
        score -= penalty
        reasons.append("low-value URL")

    include = is_homepage or score >= INCLUDE_THRESHOLD
    if penalty >= 60 and not is_homepage:
        include = False

    return RankedResource(
        resource=resource,
        score=round(score, 2),
        section=section,
        include=include,
        reason=", ".join(reasons),
    )


def _rank_sort_key(ranked: RankedResource) -> tuple[int, float, str]:
    section_priority = SECTION_PRIORITY.get(ranked.section, SECTION_PRIORITY["Optional"])
    return (section_priority, -ranked.score, ranked.resource.url)


def _base_score(resource_type: ResourceType, is_homepage: bool) -> float:
    if is_homepage:
        return 100.0
    if resource_type is ResourceType.HTML:
        return 35.0
    if resource_type is ResourceType.PDF:
        return 45.0
    if resource_type is ResourceType.IMAGE:
        return 25.0
    return 20.0


def _base_reason(resource_type: ResourceType, is_homepage: bool) -> str:
    if is_homepage:
        return "homepage"
    return str(resource_type)


def _section_for(
    resource: CrawlResource,
    path_tokens: set[str],
    metadata_tokens: set[str],
    is_homepage: bool,
) -> str:
    if is_homepage:
        return "Key Pages"
    if resource.resource_type is ResourceType.PDF:
        return "Documents"
    if resource.resource_type is ResourceType.IMAGE:
        return "Images"
    for section, keywords in SECTION_KEYWORDS:
        if _has_keyword(path_tokens, keywords):
            return section
    for section, keywords in SECTION_KEYWORDS:
        if _has_keyword(metadata_tokens, keywords):
            return section
    return "Key Pages"


def _positive_keyword_boost(section: str, resource_type: ResourceType, is_homepage: bool) -> float:
    if is_homepage:
        return 0.0
    if section in {"Documentation", "Guides"}:
        return 40.0
    if section == "Products or Services":
        return 35.0
    if section in {"Articles", "Company", "Support"}:
        return 25.0
    if resource_type is ResourceType.PDF:
        return 15.0
    if resource_type is ResourceType.IMAGE:
        return 15.0
    return 10.0


def _metadata_boost(resource: CrawlResource) -> float:
    score = 0.0
    if resource.title or resource.h1:
        score += 8.0
    if resource.description:
        score += 6.0
    if resource.link_text:
        score += 4.0
    if resource.headings:
        score += 3.0
    return score


def _low_value_penalty(path_tokens: set[str], url: str) -> float:
    matches = {keyword for keyword in LOW_VALUE_KEYWORDS if keyword in path_tokens}
    penalty = 0.0
    if matches:
        penalty += 70.0
    if urlparse(url).query:
        penalty += 15.0
    return penalty


def _has_keyword(tokens: set[str], keywords: tuple[str, ...]) -> bool:
    return any(keyword in tokens for keyword in keywords)


def _metadata_tokens(resource: CrawlResource) -> set[str]:
    text = " ".join(
        (
            resource.title,
            resource.description,
            resource.h1,
            resource.link_text,
            " ".join(resource.headings),
        )
    ).lower()
    tokens: set[str] = set()
    for raw_token in text.replace("_", "-").split():
        token = raw_token.strip(".,:;!?()[]{}\"'")
        if not token:
            continue
        tokens.add(token)
        tokens.update(part for part in token.split("-") if part)
    return tokens


def _path_tokens(url: str) -> set[str]:
    parsed = urlparse(url)
    tokens: set[str] = set()
    for part in PurePosixPath(parsed.path).parts:
        normalized = part.strip("/").lower()
        if not normalized:
            continue
        tokens.add(normalized)
        tokens.update(token for token in normalized.replace("_", "-").split("-") if token)
    return tokens


def _is_homepage(url: str, root_url: str) -> bool:
    parsed_url = urlparse(url)
    parsed_root = urlparse(root_url)
    return (
        parsed_url.scheme == parsed_root.scheme
        and parsed_url.netloc.lower() == parsed_root.netloc.lower()
        and parsed_url.path.rstrip("/") == parsed_root.path.rstrip("/")
        and not parsed_url.query
    )
