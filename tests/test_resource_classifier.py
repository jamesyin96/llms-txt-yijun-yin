from app.services.html_parser import ImageCandidate
from app.services.resource_classifier import (
    ResourceType,
    classify_image_candidate,
    classify_url,
)


def test_classifies_html_routes_as_included() -> None:
    assert classify_url("https://example.com/docs").resource_type is ResourceType.HTML
    assert classify_url("https://example.com/docs").include
    assert classify_url("https://example.com/page.html").include


def test_classifies_pdf_as_included() -> None:
    result = classify_url("https://example.com/files/report.pdf")

    assert result.resource_type is ResourceType.PDF
    assert result.include


def test_skips_static_assets() -> None:
    for url in [
        "https://example.com/app.css",
        "https://example.com/app.js",
        "https://example.com/font.woff2",
        "https://example.com/app.js.map",
        "https://example.com/video.mp4",
        "https://example.com/archive.zip",
    ]:
        result = classify_url(url)
        assert result.resource_type is ResourceType.STATIC_ASSET
        assert not result.include


def test_unknown_extension_defaults_to_included_route() -> None:
    result = classify_url("https://example.com/products/widget.custom")

    assert result.resource_type is ResourceType.UNKNOWN
    assert result.include


def test_image_url_without_context_is_not_included_yet() -> None:
    result = classify_url("https://example.com/media/photo.jpg")

    assert result.resource_type is ResourceType.IMAGE
    assert not result.include


def test_skips_icon_like_image_paths() -> None:
    for url in [
        "https://example.com/favicon.ico",
        "https://example.com/images/icon-search.png",
        "https://example.com/images/logo.svg",
        "https://example.com/images/sprite.png",
        "https://example.com/apple-touch-icon.png",
    ]:
        result = classify_image_candidate(_image(url, alt="Decorative but named like icon", width=500, height=500))
        assert result.resource_type is ResourceType.IMAGE
        assert not result.include


def test_includes_image_with_alt_text() -> None:
    result = classify_image_candidate(_image("https://example.com/media/chart.png", alt="Revenue chart"))

    assert result.resource_type is ResourceType.IMAGE
    assert result.include


def test_includes_image_with_content_like_dimensions() -> None:
    result = classify_image_candidate(
        _image("https://example.com/media/product.png", width=800, height=600)
    )

    assert result.resource_type is ResourceType.IMAGE
    assert result.include


def test_skips_tiny_images() -> None:
    result = classify_image_candidate(
        _image("https://example.com/media/tracker.png", width=32, height=32)
    )

    assert result.resource_type is ResourceType.IMAGE
    assert not result.include


def test_skips_images_without_context() -> None:
    result = classify_image_candidate(_image("https://example.com/media/unknown.png"))

    assert result.resource_type is ResourceType.IMAGE
    assert not result.include


def _image(
    url: str,
    *,
    alt: str = "",
    title: str = "",
    width: int | None = None,
    height: int | None = None,
) -> ImageCandidate:
    return ImageCandidate(
        url=url,
        alt=alt,
        title=title,
        width=width,
        height=height,
        source_url="https://example.com/",
    )

