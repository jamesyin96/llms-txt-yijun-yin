"""Scan orchestration service.

The current implementation is a scaffold: it exercises the API, database,
formatter, storage, and download path with a single homepage resource. The real
crawler will replace the placeholder block with robots-aware sitemap-first
discovery, metadata extraction, PDF/image inclusion, and retry handling.
"""

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import STORAGE_DIR
from app.db import SessionLocal
from app.models import Page, Scan
from app.services.formatter import LlmResource, render_llms_txt


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

        # Placeholder implementation for the project skeleton. The real crawler
        # will replace this with robots-aware sitemap and page discovery.
        page = Page(
            scan_id=scan.id,
            url=scan.normalized_root_url,
            canonical_url=scan.normalized_root_url,
            title=_site_name_from_url(scan.normalized_root_url),
            description=f"Homepage for {scan.normalized_root_url}",
            resource_type="html",
            section="Key Pages",
            score=100.0,
            status_code=None,
            last_crawled_at=datetime.utcnow(),
            included=True,
        )
        db.add(page)

        scan.status = "generating"
        scan.pages_found = 1
        scan.pages_included = 1
        db.commit()

        resource = LlmResource(
            title=page.title or scan.normalized_root_url,
            url=scan.normalized_root_url,
            description=page.description or "",
            section="Key Pages",
        )
        content = render_llms_txt(
            site_name=page.title or "Website",
            summary=f"Generated llms.txt for {scan.normalized_root_url}.",
            resources=[resource],
        )

        output_name = f"scan-{scan.id}-llms.txt"
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
