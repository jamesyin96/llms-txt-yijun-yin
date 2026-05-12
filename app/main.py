"""FastAPI entrypoint for the LLMs.txt Generator.

V1 exposes a deliberately small surface area:

- `GET /` serves the single-page form.
- `POST /api/scans` starts a background scan.
- `GET /api/scans?url=...` lists stored versions for one website.
- `GET /api/scans/{scan_id}` lets the browser poll status.
- `GET /download/{scan_id}` returns the generated `llms.txt`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import logging

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import (
    APP_NAME,
    BASE_DIR,
    CRAWL_MAX_DEPTH,
    CRAWL_MAX_DURATION_SECONDS,
    CRAWL_MAX_PAGES,
    DATABASE_URL,
    STORAGE_DIR,
)
from app.db import SessionLocal, get_db, init_db
from app.models import Scan
from app.schemas import (
    ScanChangeSummary,
    ScanCreate,
    ScanCreated,
    ScanHistory,
    ScanHistoryItem,
    ScanStatus,
)
from app.services.change_detector import parse_change_summary
from app.services.scanner import run_scan
from app.services.security import UnsafeUrlError, assert_safe_url
from app.services.url_utils import normalize_root_url


logger = logging.getLogger("uvicorn.error")
REFRESH_LOOKBACK_HOURS = 12


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Prepare storage and SQLite tables when the app starts.

    FastAPI now recommends lifespan handlers over `@app.on_event("startup")`.
    Keeping initialization here avoids deprecation warnings while preserving
    the same behavior: run `init_db()` once during application startup.
    """

    init_db()
    _log_startup_state()
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


@app.get("/")
def index(request: Request):
    """Render the minimal URL input page."""

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_name": APP_NAME,
            "crawl_max_pages": CRAWL_MAX_PAGES,
            "crawl_max_depth": CRAWL_MAX_DEPTH,
            "crawl_max_duration_seconds": CRAWL_MAX_DURATION_SECONDS,
        },
    )


@app.post("/api/scans", response_model=ScanCreated)
def create_scan(
    payload: ScanCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ScanCreated:
    """Create a scan record and schedule the scan work.

    The current skeleton normalizes the URL and runs immediate SSRF-oriented
    safety checks before queueing the task. DNS and redirect checks are applied
    by the fetch layer immediately before real network requests.
    """

    try:
        normalized_url = normalize_root_url(payload.url)
        assert_safe_url(normalized_url)
    except (ValueError, UnsafeUrlError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = _latest_completed_scan_within(db, normalized_url, hours=REFRESH_LOOKBACK_HOURS)
    if existing is not None:
        existing.auto_refresh_daily = payload.auto_refresh_daily or existing.auto_refresh_daily
        db.commit()
        return ScanCreated(
            scan_id=existing.id,
            version_number=existing.version_number,
            crawl_max_pages=existing.crawl_max_pages,
            crawl_max_depth=existing.crawl_max_depth,
            crawl_max_duration_seconds=existing.crawl_max_duration_seconds,
            auto_refresh_daily=existing.auto_refresh_daily,
            reused_existing=True,
            status=existing.status,
        )

    scan = Scan(
        root_url=payload.url,
        normalized_root_url=normalized_url,
        version_number=_next_version_number(db, normalized_url),
        crawl_max_pages=payload.crawl_max_pages,
        crawl_max_depth=payload.crawl_max_depth,
        crawl_max_duration_seconds=payload.crawl_max_duration_seconds,
        auto_refresh_daily=payload.auto_refresh_daily,
        status="queued",
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    logger.info(
        "scan_created scan_id=%s version=%s root_url=%s normalized_root_url=%s "
        "max_pages=%s max_depth=%s time_budget_seconds=%s",
        scan.id,
        scan.version_number,
        scan.root_url,
        scan.normalized_root_url,
        scan.crawl_max_pages,
        scan.crawl_max_depth,
        scan.crawl_max_duration_seconds,
    )

    background_tasks.add_task(run_scan, scan.id)
    return ScanCreated(
        scan_id=scan.id,
        version_number=scan.version_number,
        crawl_max_pages=scan.crawl_max_pages,
        crawl_max_depth=scan.crawl_max_depth,
        crawl_max_duration_seconds=scan.crawl_max_duration_seconds,
        auto_refresh_daily=scan.auto_refresh_daily,
        reused_existing=False,
        status=scan.status,
    )


@app.get("/api/scans", response_model=ScanHistory)
def list_scans(url: str, db: Session = Depends(get_db)) -> ScanHistory:
    """Return stored scan versions for a normalized website URL."""

    try:
        normalized_url = normalize_root_url(url)
        assert_safe_url(normalized_url)
    except (ValueError, UnsafeUrlError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scans = (
        db.query(Scan)
        .filter(Scan.normalized_root_url == normalized_url)
        .order_by(Scan.version_number.desc(), Scan.id.desc())
        .limit(10)
        .all()
    )
    return ScanHistory(
        root_url=normalized_url,
        scans=[_scan_history_item(scan) for scan in scans],
    )


@app.get("/api/scans/{scan_id}", response_model=ScanStatus)
def get_scan(scan_id: int, db: Session = Depends(get_db)) -> ScanStatus:
    """Return scan progress for frontend polling."""

    scan = db.get(Scan, scan_id)
    if scan is None:
        logger.warning(
            "scan_not_found scan_id=%s scan_count=%s storage_dir=%s database_url=%s",
            scan_id,
            _scan_count(db),
            STORAGE_DIR,
            DATABASE_URL,
        )
        raise HTTPException(status_code=404, detail="Scan not found")

    return ScanStatus(
        scan_id=scan.id,
        version_number=scan.version_number,
        crawl_max_pages=scan.crawl_max_pages,
        crawl_max_depth=scan.crawl_max_depth,
        crawl_max_duration_seconds=scan.crawl_max_duration_seconds,
        auto_refresh_daily=scan.auto_refresh_daily,
        previous_scan_id=scan.previous_scan_id,
        change_summary=_change_summary_for(scan),
        status=scan.status,
        root_url=scan.normalized_root_url,
        pages_found=scan.pages_found,
        pages_included=scan.pages_included,
        download_url=_download_url_for(scan),
        error=scan.error,
    )


@app.get("/download/{scan_id}")
def download_scan(scan_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """Download the generated `llms.txt` file for a completed scan."""

    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.status != "complete" or not scan.output_path:
        raise HTTPException(status_code=404, detail="Generated file is not ready")

    output_path = STORAGE_DIR / scan.output_path
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Generated file no longer exists")

    return FileResponse(
        output_path,
        media_type="text/plain",
        filename=f"llms-v{scan.version_number}.txt",
    )


def _scan_history_item(scan: Scan) -> ScanHistoryItem:
    """Convert a scan row into the compact history shape used by the UI."""

    return ScanHistoryItem(
        scan_id=scan.id,
        version_number=scan.version_number,
        crawl_max_pages=scan.crawl_max_pages,
        crawl_max_depth=scan.crawl_max_depth,
        crawl_max_duration_seconds=scan.crawl_max_duration_seconds,
        auto_refresh_daily=scan.auto_refresh_daily,
        previous_scan_id=scan.previous_scan_id,
        change_summary=_change_summary_for(scan),
        status=scan.status,
        pages_found=scan.pages_found,
        pages_included=scan.pages_included,
        download_url=_download_url_for(scan),
        created_at=scan.created_at,
        finished_at=scan.finished_at,
        error=scan.error,
    )


def _download_url_for(scan: Scan) -> str | None:
    """Return a download URL only when a completed scan has an output file."""

    if scan.status == "complete" and scan.output_path:
        return f"/download/{scan.id}"
    return None


def _change_summary_for(scan: Scan) -> ScanChangeSummary | None:
    """Parse a stored change summary into the API response shape."""

    summary = parse_change_summary(scan.change_summary)
    if summary is None:
        return None
    return ScanChangeSummary(
        added=summary.added,
        removed=summary.removed,
        changed=summary.changed,
        unchanged=summary.unchanged,
    )


def _next_version_number(db: Session, normalized_root_url: str) -> int:
    """Return the next per-site version number for a normalized root URL."""

    current_max = db.query(func.max(Scan.version_number)).filter(
        Scan.normalized_root_url == normalized_root_url
    ).scalar()
    return (current_max or 0) + 1


def _latest_completed_scan_within(db: Session, normalized_root_url: str, *, hours: int) -> Scan | None:
    threshold = datetime.utcnow() - timedelta(hours=hours)
    return (
        db.query(Scan)
        .filter(Scan.normalized_root_url == normalized_root_url)
        .filter(Scan.status == "complete")
        .filter(Scan.created_at >= threshold)
        .order_by(Scan.version_number.desc(), Scan.id.desc())
        .first()
    )


def _log_startup_state() -> None:
    db = SessionLocal()
    try:
        logger.info(
            "app_startup storage_dir=%s database_url=%s scan_count=%s "
            "default_max_pages=%s default_max_depth=%s default_time_budget_seconds=%s",
            STORAGE_DIR,
            DATABASE_URL,
            _scan_count(db),
            CRAWL_MAX_PAGES,
            CRAWL_MAX_DEPTH,
            CRAWL_MAX_DURATION_SECONDS,
        )
    except Exception:
        logger.exception(
            "app_startup_state_failed storage_dir=%s database_url=%s",
            STORAGE_DIR,
            DATABASE_URL,
        )
    finally:
        db.close()


def _scan_count(db: Session) -> int:
    return db.query(func.count(Scan.id)).scalar() or 0
