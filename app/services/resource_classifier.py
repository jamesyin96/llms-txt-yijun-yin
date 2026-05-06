"""Resource classification and inclusion rules.

The crawler discovers many URL-like resources. This module decides what each
resource appears to be and whether it belongs in the crawl/output set. Keeping
these rules centralized makes the crawler easier to explain and tune.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from urllib.parse import urlparse

from app.services.html_parser import ImageCandidate


class ResourceType(StrEnum):
    """Resource categories used by the crawler and stored page records."""

    HTML = "html"
    PDF = "pdf"
    IMAGE = "image"
    STATIC_ASSET = "static_asset"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ResourceClassification:
    """Classification result for one discovered URL."""

    resource_type: ResourceType
    include: bool
    reason: str


HTML_EXTENSIONS = {"", ".html", ".htm", ".xhtml", ".php", ".asp", ".aspx"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".avif", ".bmp", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
STATIC_ASSET_EXTENSIONS = {
    ".7z",
    ".avi",
    ".css",
    ".csv",
    ".doc",
    ".docx",
    ".eot",
    ".gz",
    ".js",
    ".json",
    ".map",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ogg",
    ".otf",
    ".rar",
    ".tar",
    ".tgz",
    ".ttf",
    ".wasm",
    ".wav",
    ".woff",
    ".woff2",
    ".xls",
    ".xlsx",
    ".xml",
    ".zip",
}

DECORATIVE_IMAGE_HINTS = {
    "apple-touch-icon",
    "badge",
    "favicon",
    "icon",
    "logo",
    "placeholder",
    "sprite",
}
MIN_MEANINGFUL_IMAGE_DIMENSION = 120


def classify_url(url: str) -> ResourceClassification:
    """Classify a URL without page-specific image context."""

    extension = _extension_for_url(url)
    if extension in PDF_EXTENSIONS:
        return ResourceClassification(ResourceType.PDF, True, "PDF resources are included.")
    if extension in IMAGE_EXTENSIONS:
        if _has_decorative_image_hint(url):
            return ResourceClassification(
                ResourceType.IMAGE,
                False,
                "Image URL looks decorative or icon-like.",
            )
        return ResourceClassification(
            ResourceType.IMAGE,
            False,
            "Image needs page context before inclusion.",
        )
    if extension in STATIC_ASSET_EXTENSIONS:
        return ResourceClassification(
            ResourceType.STATIC_ASSET,
            False,
            "Static assets are skipped.",
        )
    if extension in HTML_EXTENSIONS:
        return ResourceClassification(ResourceType.HTML, True, "HTML page candidate.")
    return ResourceClassification(ResourceType.UNKNOWN, True, "Unknown extension treated as HTML route.")


def classify_image_candidate(image: ImageCandidate) -> ResourceClassification:
    """Classify an image discovered from HTML with alt/dimension context."""

    base = classify_url(image.url)
    if base.resource_type is not ResourceType.IMAGE:
        return base
    if not base.include and base.reason != "Image needs page context before inclusion.":
        return base
    if _has_decorative_image_hint(image.url):
        return ResourceClassification(
            ResourceType.IMAGE,
            False,
            "Image URL looks decorative or icon-like.",
        )
    if image.alt:
        return ResourceClassification(ResourceType.IMAGE, True, "Image has meaningful alt text.")
    if _has_meaningful_dimensions(image):
        return ResourceClassification(ResourceType.IMAGE, True, "Image dimensions look content-like.")
    if _has_tiny_dimensions(image):
        return ResourceClassification(ResourceType.IMAGE, False, "Image dimensions look icon-sized.")
    return ResourceClassification(
        ResourceType.IMAGE,
        False,
        "Image lacks alt text or useful dimensions.",
    )


def _extension_for_url(url: str) -> str:
    path = urlparse(url).path
    return PurePosixPath(path).suffix.lower()


def _has_decorative_image_hint(url: str) -> bool:
    normalized_path = urlparse(url).path.lower()
    return any(hint in normalized_path for hint in DECORATIVE_IMAGE_HINTS)


def _has_meaningful_dimensions(image: ImageCandidate) -> bool:
    if image.width is None or image.height is None:
        return False
    return (
        image.width >= MIN_MEANINGFUL_IMAGE_DIMENSION
        and image.height >= MIN_MEANINGFUL_IMAGE_DIMENSION
    )


def _has_tiny_dimensions(image: ImageCandidate) -> bool:
    if image.width is None or image.height is None:
        return False
    return (
        image.width < MIN_MEANINGFUL_IMAGE_DIMENSION
        or image.height < MIN_MEANINGFUL_IMAGE_DIMENSION
    )
