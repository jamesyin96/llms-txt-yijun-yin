"""Pydantic request and response models for the scan API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ScanCreate(BaseModel):
    """Payload submitted by the browser when a user starts a scan."""

    url: str


class ScanCreated(BaseModel):
    """Initial response returned after a scan record has been queued."""

    scan_id: int
    version_number: int
    status: str


class ScanChangeSummary(BaseModel):
    """Compact added/removed/changed counts for a re-scan."""

    added: int
    removed: int
    changed: int
    unchanged: int


class ScanStatus(BaseModel):
    """Polling response used by the browser while a scan is running."""

    scan_id: int
    version_number: int
    previous_scan_id: Optional[int] = None
    change_summary: Optional[ScanChangeSummary] = None
    status: str
    root_url: str
    pages_found: int
    pages_included: int
    download_url: Optional[str] = None
    error: Optional[str] = None


class ScanHistoryItem(BaseModel):
    """One previous scan version for a normalized website URL."""

    scan_id: int
    version_number: int
    previous_scan_id: Optional[int] = None
    change_summary: Optional[ScanChangeSummary] = None
    status: str
    pages_found: int
    pages_included: int
    download_url: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None
    error: Optional[str] = None


class ScanHistory(BaseModel):
    """Version history returned for one normalized website URL."""

    root_url: str
    scans: list[ScanHistoryItem]
