"""Database setup for the local SQLite-backed application.

Render free-tier deployments use the same SQLite file under `storage/`, with
the known caveat that the filesystem is ephemeral. For V1 this is acceptable
because generated downloads are only expected to survive during an active demo
session.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATABASE_URL, STORAGE_DIR


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
