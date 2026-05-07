"""SQLAlchemy models for V1 scan persistence.

The implementation plan intentionally keeps the first database shape small:
`Scan` records the lifecycle of one URL scan, and `Page` records resources
discovered during that scan. Re-scan/change tracking can build on top of these
tables later.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Scan(Base):
    """A single requested website scan and its generated output state."""

    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    root_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    normalized_root_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    pages_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pages_included: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_path: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    previous_scan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    pages: Mapped[list["Page"]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
    )


class Page(Base):
    """One HTML page, PDF, or meaningful image discovered during a scan."""

    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resource_type: Mapped[str] = mapped_column(String(32), default="html", nullable=False)
    section: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    included: Mapped[bool] = mapped_column(default=True, nullable=False)

    scan: Mapped[Scan] = relationship(back_populates="pages")
