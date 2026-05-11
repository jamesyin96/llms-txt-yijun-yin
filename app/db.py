"""Database setup for the local SQLite-backed application.

By default, SQLite and generated outputs live under `storage/`. For hosted
deployments, set `STORAGE_DIR` (for example `/var/data`) to place both the
database and generated files on a persistent volume.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import (
    CRAWL_MAX_DEPTH,
    CRAWL_MAX_DURATION_SECONDS,
    CRAWL_MAX_PAGES,
    DATABASE_URL,
    STORAGE_DIR,
)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""

    pass


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create local storage and database tables if they do not exist.

    This project intentionally avoids Alembic for the V1 local/demo setup. Tiny
    additive SQLite migrations live here until the schema becomes large enough
    to justify a migration tool.
    """

    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _run_lightweight_migrations()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides one SQLAlchemy session per request."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _run_lightweight_migrations() -> None:
    """Apply small additive SQLite migrations for existing local databases."""

    inspector = inspect(engine)
    if "scans" not in inspector.get_table_names():
        return

    scan_columns = {column["name"] for column in inspector.get_columns("scans")}
    if "version_number" not in scan_columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE scans ADD COLUMN version_number INTEGER NOT NULL DEFAULT 1")
            )
    _add_column_if_missing(
        scan_columns,
        "crawl_max_pages",
        f"INTEGER NOT NULL DEFAULT {CRAWL_MAX_PAGES}",
    )
    _add_column_if_missing(
        scan_columns,
        "crawl_max_depth",
        f"INTEGER NOT NULL DEFAULT {CRAWL_MAX_DEPTH}",
    )
    _add_column_if_missing(
        scan_columns,
        "crawl_max_duration_seconds",
        f"FLOAT NOT NULL DEFAULT {CRAWL_MAX_DURATION_SECONDS}",
    )
    _backfill_scan_versions()


def _add_column_if_missing(existing_columns: set[str], column_name: str, definition: str) -> None:
    if column_name in existing_columns:
        return
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE scans ADD COLUMN {column_name} {definition}"))


def _backfill_scan_versions() -> None:
    """Keep existing scan rows on a consecutive per-site version sequence."""

    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT id, normalized_root_url, version_number, output_path
                FROM scans
                ORDER BY normalized_root_url ASC, created_at ASC, id ASC
                """
            )
        ).mappings()

        next_versions: dict[str, int] = {}
        for row in rows:
            root_url = row["normalized_root_url"]
            version_number = next_versions.get(root_url, 1)
            next_versions[root_url] = version_number + 1

            if row["version_number"] != version_number:
                connection.execute(
                    text("UPDATE scans SET version_number = :version_number WHERE id = :scan_id"),
                    {"version_number": version_number, "scan_id": row["id"]},
                )
            _backfill_scan_output_path(connection, row["id"], version_number, row["output_path"])


def _backfill_scan_output_path(
    connection: Connection,
    scan_id: int,
    version_number: int,
    output_path: str | None,
) -> None:
    """Rename old generated files to match the backfilled version number."""

    if not output_path:
        return

    desired_name = f"scan-{scan_id}-v{version_number}-llms.txt"
    if output_path == desired_name:
        return

    current_path = STORAGE_DIR / output_path
    desired_path = STORAGE_DIR / desired_name
    if current_path.exists() and not desired_path.exists():
        current_path.rename(desired_path)

    if desired_path.exists():
        connection.execute(
            text("UPDATE scans SET output_path = :output_path WHERE id = :scan_id"),
            {"output_path": desired_name, "scan_id": scan_id},
        )
