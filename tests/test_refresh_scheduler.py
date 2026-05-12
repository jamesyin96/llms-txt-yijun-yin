from datetime import datetime, timedelta

from app.db import SessionLocal, init_db
from app.models import Scan
from app.services.refresh_scheduler import queue_due_auto_refresh_scans


init_db()


def test_queue_due_auto_refresh_scans_queues_for_stale_refresh_enabled_site() -> None:
    db = SessionLocal()
    try:
        base = Scan(
            root_url="https://refresh-stale.example.com/",
            normalized_root_url="https://refresh-stale.example.com/",
            version_number=1,
            status="complete",
            auto_refresh_daily=True,
            created_at=datetime.utcnow() - timedelta(hours=13),
        )
        db.add(base)
        db.commit()

        queued = queue_due_auto_refresh_scans(db)

        assert len(queued) == 1
        next_scan = db.get(Scan, queued[0])
        assert next_scan is not None
        assert next_scan.normalized_root_url == base.normalized_root_url
        assert next_scan.version_number == 2
        assert next_scan.status == "queued"
    finally:
        db.close()


def test_queue_due_auto_refresh_scans_skips_recent_scan() -> None:
    db = SessionLocal()
    try:
        recent = Scan(
            root_url="https://refresh-recent.example.com/",
            normalized_root_url="https://refresh-recent.example.com/",
            version_number=1,
            status="complete",
            auto_refresh_daily=True,
            created_at=datetime.utcnow() - timedelta(hours=2),
        )
        db.add(recent)
        db.commit()

        queued = queue_due_auto_refresh_scans(db)

        assert queued == []
    finally:
        db.close()


def test_queue_due_auto_refresh_scans_skips_when_auto_refresh_disabled() -> None:
    db = SessionLocal()
    try:
        disabled = Scan(
            root_url="https://refresh-disabled.example.com/",
            normalized_root_url="https://refresh-disabled.example.com/",
            version_number=1,
            status="complete",
            auto_refresh_daily=False,
            created_at=datetime.utcnow() - timedelta(hours=30),
        )
        db.add(disabled)
        db.commit()

        queued = queue_due_auto_refresh_scans(db)

        assert queued == []
    finally:
        db.close()
