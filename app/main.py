"""FastAPI entrypoint for the LLMs.txt Generator.

V1 exposes a deliberately small surface area:

- `GET /` serves the single-page form.
- `POST /api/scans` starts a background scan.
- `GET /api/scans/{scan_id}` lets the browser poll status.
- `GET /download/{scan_id}` returns the generated `llms.txt`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import APP_NAME, BASE_DIR, STORAGE_DIR
from app.db import get_db, init_db
from app.models import Scan
from app.schemas import ScanCreate, ScanCreated, ScanStatus
from app.services.scanner import run_scan
from app.services.security import UnsafeUrlError, assert_safe_url
from app.services.url_utils import normalize_root_url


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Prepare storage and SQLite tables when the app starts.

    FastAPI now recommends lifespan handlers over `@app.on_event("startup")`.
    Keeping initialization here avoids deprecation warnings while preserving
    the same behavior: run `init_db()` once during application startup.
    """

    init_db()
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


@app.get("/")
def index(request: Request):
    """Render the minimal URL input page."""

    return templates.TemplateResponse(request, "index.html", {"app_name": APP_NAME})


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

    scan = Scan(
        root_url=payload.url,
        normalized_root_url=normalized_url,
        status="queued",
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    background_tasks.add_task(run_scan, scan.id)
    return ScanCreated(scan_id=scan.id, status=scan.status)


@app.get("/api/scans/{scan_id}", response_model=ScanStatus)
def get_scan(scan_id: int, db: Session = Depends(get_db)) -> ScanStatus:
    """Return scan progress for frontend polling."""

    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    return ScanStatus(
        scan_id=scan.id,
        status=scan.status,
        root_url=scan.normalized_root_url,
        pages_found=scan.pages_found,
        pages_included=scan.pages_included,
        download_url=f"/download/{scan.id}" if scan.status == "complete" else None,
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
        filename="llms.txt",
    )
