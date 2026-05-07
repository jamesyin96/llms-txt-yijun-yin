"""Scan orchestration service.

This module bridges the web/API layer, crawler, database, formatter, and local
file storage. The crawler returns plain dataclasses; the scanner persists those
resources and renders the downloadable llms.txt file.
"""

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import STORAGE_DIR
from app.db import SessionLocal
from app.models import Page, Scan
from app.services.crawler import CrawlConfig, CrawlResource, crawl_site
from app.services.formatter import LlmResource, render_llms_txt, validate_llms_txt
from app.services.resource_classifier import ResourceType


def run_scan(scan_id: int) -> None:
    """Entry point used by FastAPI background tasks."""

    db = SessionLocal()
    try:
        _run_scan(scan_id, db)
    finally:
        db.close()


def _run_scan(scan_id: int, db: Session) -> None:
    """Run one scan and persist its generated output.

    This function owns the scan status transitions:
    queued -> crawling -> generating -> complete, or failed on error.
    """

    scan = db.get(Scan, scan_id)
    if scan is None:
        return

    try:
        scan.status = "crawling"
        db.commit()

        crawl_result = crawl_site(
            scan.normalized_root_url,
            crawl_config=CrawlConfig(max_pages=100, max_depth=2),
        )
        pages = [_page_from_resource(scan.id, resource) for resource in crawl_result.resources]
        db.add_all(pages)

        scan.status = "generating"
        scan.pages_found = len(crawl_result.resources) + len(crawl_result.skipped)
        scan.pages_included = len(crawl_result.resources)
        db.commit()

        content = render_llms_txt(
            site_name=_site_name_from_crawl(crawl_result.resources, scan.normalized_root_url),
            summary=_summary_from_crawl(crawl_result.resources, scan.normalized_root_url),
            resources=_llm_resources_from_crawl(crawl_result.resources),
        )
        validation = validate_llms_txt(content)
        if not validation.valid:
            raise ValueError(f"Generated llms.txt failed validation: {'; '.join(validation.errors)}")

        output_name = f"scan-{scan.id}-v{scan.version_number}-llms.txt"
        output_path = Path(output_name)
        (STORAGE_DIR / output_path).write_text(content, encoding="utf-8")

        scan.output_path = str(output_path)
        scan.status = "complete"
        scan.finished_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        scan.status = "failed"
        scan.error = str(exc)
        scan.finished_at = datetime.utcnow()
        db.commit()


def _site_name_from_url(url: str) -> str:
    """Derive a readable fallback site name from a normalized URL."""

    host = url.split("//", 1)[-1].split("/", 1)[0]
    return host.removeprefix("www.")


def _page_from_resource(scan_id: int, resource: CrawlResource) -> Page:
    """Convert a crawler resource into a persisted page record."""

    return Page(
        scan_id=scan_id,
        url=resource.url,
        canonical_url=resource.canonical_url,
        title=_resource_title(resource),
        description=_resource_description(resource),
        resource_type=str(resource.resource_type),
        section=_section_for_resource(resource),
        score=0.0,
        status_code=resource.status_code,
        content_hash=resource.content_hash,
        last_crawled_at=datetime.utcnow(),
        included=True,
    )


def _llm_resources_from_crawl(resources: tuple[CrawlResource, ...]) -> list[LlmResource]:
    return [
        LlmResource(
            title=_resource_title(resource),
            url=resource.url,
            description=_resource_description(resource),
            section=_section_for_resource(resource),
        )
        for resource in resources
    ]


def _site_name_from_crawl(resources: tuple[CrawlResource, ...], root_url: str) -> str:
    homepage = next((resource for resource in resources if resource.url == root_url), None)
    if homepage:
        return homepage.title or homepage.h1 or _site_name_from_url(root_url)
    first_html = next((resource for resource in resources if resource.resource_type is ResourceType.HTML), None)
    if first_html:
        return first_html.title or first_html.h1 or _site_name_from_url(root_url)
    return _site_name_from_url(root_url)


def _summary_from_crawl(resources: tuple[CrawlResource, ...], root_url: str) -> str:
    homepage = next((resource for resource in resources if resource.url == root_url), None)
    if homepage and homepage.description:
        return homepage.description
    first_description = next((resource.description for resource in resources if resource.description), "")
    return first_description or f"Generated llms.txt for {root_url}."


def _resource_title(resource: CrawlResource) -> str:
    return (
        resource.title
        or resource.h1
        or resource.link_text
        or _filename_title(resource.url)
        or resource.url
    )


def _resource_description(resource: CrawlResource) -> str:
    if resource.description:
        return resource.description
    if resource.resource_type is ResourceType.PDF:
        return resource.link_text or "PDF resource."
    if resource.resource_type is ResourceType.IMAGE:
        return resource.link_text or "Image resource."
    return resource.link_text or ""


def _section_for_resource(resource: CrawlResource) -> str:
    if resource.resource_type is ResourceType.PDF:
        return "Documents"
    if resource.resource_type is ResourceType.IMAGE:
        return "Images"
    path = _path_for_section(resource.url)
    if any(part in path for part in ("/docs", "/documentation", "/reference", "/api")):
        return "Documentation"
    if any(part in path for part in ("/guide", "/guides", "/tutorial", "/learn")):
        return "Guides"
    if any(part in path for part in ("/blog", "/weblog", "/news", "/articles")):
        return "Articles"
    if any(part in path for part in ("/about", "/company", "/team", "/careers")):
        return "Company"
    if any(part in path for part in ("/support", "/help", "/contact", "/faq")):
        return "Support"
    return "Key Pages"


def _filename_title(url: str) -> str:
    path = url.split("?", 1)[0].rstrip("/")
    filename = path.rsplit("/", 1)[-1]
    return filename.replace("-", " ").replace("_", " ").strip()


def _path_for_section(url: str) -> str:
    path = url.split("://", 1)[-1].split("/", 1)
    if len(path) == 1:
        return "/"
    return f"/{path[1].lower()}"
