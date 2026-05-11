"""Scan orchestration service.

This module bridges the web/API layer, crawler, database, formatter, and local
file storage. The crawler returns plain dataclasses; the scanner persists those
resources and renders the downloadable llms.txt file.
"""

from datetime import datetime
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import CRAWL_MAX_CONCURRENCY, STORAGE_DIR
from app.db import SessionLocal
from app.models import Page, Scan
from app.services.change_detector import summarize_changes
from app.services.crawler import CrawlConfig, CrawlResource, crawl_site
from app.services.formatter import LlmResource, render_llms_txt, validate_llms_txt
from app.services.ranker import RankedResource, rank_resources
from app.services.resource_classifier import ResourceType


logger = logging.getLogger("uvicorn.error")


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
        logger.warning("scan_background_missing scan_id=%s", scan_id)
        return

    try:
        scan.status = "crawling"
        db.commit()
        logger.info(
            "scan_status scan_id=%s status=%s normalized_root_url=%s "
            "max_pages=%s max_depth=%s time_budget_seconds=%s",
            scan.id,
            scan.status,
            scan.normalized_root_url,
            scan.crawl_max_pages,
            scan.crawl_max_depth,
            scan.crawl_max_duration_seconds,
        )

        crawl_result = crawl_site(
            scan.normalized_root_url,
            crawl_config=CrawlConfig(
                max_pages=scan.crawl_max_pages,
                max_depth=scan.crawl_max_depth,
                max_duration_seconds=scan.crawl_max_duration_seconds,
                max_concurrency=CRAWL_MAX_CONCURRENCY,
            ),
        )
        ranked_resources = rank_resources(crawl_result.resources, scan.normalized_root_url)
        pages = [_page_from_ranked_resource(scan.id, ranked) for ranked in ranked_resources]
        db.add_all(pages)

        scan.status = "generating"
        scan.pages_found = len(crawl_result.resources) + len(crawl_result.skipped)
        scan.pages_included = len(ranked_resources)
        db.commit()
        logger.info(
            "scan_status scan_id=%s status=%s normalized_root_url=%s "
            "pages_found=%s pages_included=%s max_pages=%s max_depth=%s time_budget_seconds=%s",
            scan.id,
            scan.status,
            scan.normalized_root_url,
            scan.pages_found,
            scan.pages_included,
            scan.crawl_max_pages,
            scan.crawl_max_depth,
            scan.crawl_max_duration_seconds,
        )

        content = render_llms_txt(
            site_name=_site_name_from_crawl(crawl_result.resources, scan.normalized_root_url),
            summary=_summary_from_crawl(crawl_result.resources, scan.normalized_root_url),
            resources=_llm_resources_from_ranked(ranked_resources),
        )
        validation = validate_llms_txt(content)
        if not validation.valid:
            raise ValueError(f"Generated llms.txt failed validation: {'; '.join(validation.errors)}")

        output_name = f"scan-{scan.id}-v{scan.version_number}-llms.txt"
        output_path = Path(output_name)
        (STORAGE_DIR / output_path).write_text(content, encoding="utf-8")

        previous_scan = _previous_completed_scan(db, scan)
        if previous_scan is not None:
            scan.previous_scan_id = previous_scan.id
            previous_pages = _included_pages_for_scan(db, previous_scan.id)
            current_pages = _included_pages_for_scan(db, scan.id)
            scan.change_summary = summarize_changes(previous_pages, current_pages).to_json()

        scan.output_path = str(output_path)
        scan.status = "complete"
        scan.finished_at = datetime.utcnow()
        db.commit()
        logger.info(
            "scan_status scan_id=%s status=%s normalized_root_url=%s "
            "pages_found=%s pages_included=%s output_path=%s max_pages=%s max_depth=%s "
            "time_budget_seconds=%s",
            scan.id,
            scan.status,
            scan.normalized_root_url,
            scan.pages_found,
            scan.pages_included,
            scan.output_path,
            scan.crawl_max_pages,
            scan.crawl_max_depth,
            scan.crawl_max_duration_seconds,
        )
    except Exception as exc:
        scan.status = "failed"
        scan.error = str(exc)
        scan.finished_at = datetime.utcnow()
        db.commit()
        logger.exception(
            "scan_status scan_id=%s status=%s normalized_root_url=%s error=%s "
            "max_pages=%s max_depth=%s time_budget_seconds=%s",
            scan.id,
            scan.status,
            scan.normalized_root_url,
            scan.error,
            scan.crawl_max_pages,
            scan.crawl_max_depth,
            scan.crawl_max_duration_seconds,
        )


def _site_name_from_url(url: str) -> str:
    """Derive a readable fallback site name from a normalized URL."""

    host = url.split("//", 1)[-1].split("/", 1)[0]
    return host.removeprefix("www.")


def _previous_completed_scan(db: Session, scan: Scan) -> Scan | None:
    """Find the newest completed scan for the same site before this scan."""

    return (
        db.query(Scan)
        .filter(Scan.normalized_root_url == scan.normalized_root_url)
        .filter(Scan.status == "complete")
        .filter(Scan.id != scan.id)
        .order_by(Scan.version_number.desc(), Scan.id.desc())
        .first()
    )


def _included_pages_for_scan(db: Session, scan_id: int) -> list[Page]:
    """Return included page snapshots for change detection."""

    return (
        db.query(Page)
        .filter(Page.scan_id == scan_id)
        .filter(Page.included.is_(True))
        .order_by(Page.id.asc())
        .all()
    )


def _page_from_ranked_resource(scan_id: int, ranked: RankedResource) -> Page:
    """Convert a ranked crawler resource into a persisted page record."""

    resource = ranked.resource

    return Page(
        scan_id=scan_id,
        url=resource.url,
        canonical_url=resource.canonical_url,
        title=_resource_title(resource),
        description=_resource_description(resource),
        resource_type=str(resource.resource_type),
        section=ranked.section,
        score=ranked.score,
        status_code=resource.status_code,
        content_hash=resource.content_hash,
        last_crawled_at=datetime.utcnow(),
        included=ranked.include,
    )


def _llm_resources_from_ranked(ranked_resources: list[RankedResource]) -> list[LlmResource]:
    return [
        LlmResource(
            title=_resource_title(ranked.resource),
            url=ranked.resource.url,
            description=_resource_description(ranked.resource),
            section=ranked.section,
        )
        for ranked in ranked_resources
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


def _filename_title(url: str) -> str:
    path = url.split("?", 1)[0].rstrip("/")
    filename = path.rsplit("/", 1)[-1]
    return filename.replace("-", " ").replace("_", " ").strip()
