"""Pydantic request and response models for the scan API."""

from typing import Optional

from pydantic import BaseModel


class ScanCreate(BaseModel):
    """Payload submitted by the browser when a user starts a scan."""

    url: str


class ScanCreated(BaseModel):
    """Initial response returned after a scan record has been queued."""

    scan_id: int
    status: str


class ScanStatus(BaseModel):
    """Polling response used by the browser while a scan is running."""

    scan_id: int
    status: str
    root_url: str
    pages_found: int
    pages_included: int
    download_url: Optional[str] = None
    error: Optional[str] = None
