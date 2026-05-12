"""Periodic auto-refresh scheduler for refresh-enabled sites."""

from datetime import datetime, timedelta
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import AUTO_REFRESH_LOOKBACK_HOURS
from app.models import Scan


logger = logging.getLogger("uvicorn.error")
ACTIVE_SCAN_STATUSES = ("queued", "crawling", "generating")


def queue_due_auto_refresh_scans(db: Session) -> list[int]:
    """Create queued scans for refresh-enabled sites that are stale.

    A site is considered due when the latest scan row for that normalized root
    URL is older than 12 hours.
    """

    stale_before = datetime.utcnow() - timedelta(hours=AUTO_REFRESH_LOOKBACK_HOURS)
    logger.info(
        "auto_refresh_cycle_start lookback_hours=%s stale_before=%s",
        AUTO_REFRESH_LOOKBACK_HOURS,
        stale_before.isoformat(),
    )
    stale_roots = (
        db.query(Scan.normalized_root_url)
        .filter(Scan.auto_refresh_daily.is_(True))
        .group_by(Scan.normalized_root_url)
        .having(func.max(Scan.created_at) < stale_before)
        .all()
    )

    logger.info("auto_refresh_candidates count=%s", len(stale_roots))

    queued_ids: list[int] = []
    for (root_url,) in stale_roots:
        latest = (
            db.query(Scan)
            .filter(Scan.normalized_root_url == root_url)
            .order_by(Scan.version_number.desc(), Scan.id.desc())
            .first()
        )
        if latest is None:
            logger.warning("auto_refresh_candidate_missing_latest normalized_root_url=%s", root_url)
            continue
        if latest.status in ACTIVE_SCAN_STATUSES:
            logger.info(
                "auto_refresh_candidate_active normalized_root_url=%s status=%s",
                root_url,
                latest.status,
            )
            continue

        next_version = (latest.version_number or 0) + 1
        queued = Scan(
            root_url=latest.root_url,
            normalized_root_url=latest.normalized_root_url,
            version_number=next_version,
            crawl_max_pages=latest.crawl_max_pages,
            crawl_max_depth=latest.crawl_max_depth,
            crawl_max_duration_seconds=latest.crawl_max_duration_seconds,
            auto_refresh_daily=True,
            status="queued",
        )
        db.add(queued)
        db.commit()
        db.refresh(queued)
        queued_ids.append(queued.id)
        logger.info(
            "auto_refresh_queued scan_id=%s normalized_root_url=%s version=%s",
            queued.id,
            queued.normalized_root_url,
            queued.version_number,
        )

    logger.info("auto_refresh_cycle_complete queued_count=%s", len(queued_ids))
    return queued_ids
