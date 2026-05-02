"""Database setup for the local SQLite-backed application.

Render free-tier deployments use the same SQLite file under `storage/`, with
the known caveat that the filesystem is ephemeral. For V1 this is acceptable
because generated downloads are only expected to survive during an active demo
session.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
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
    """Create local storage and database tables if they do not exist."""

    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides one SQLAlchemy session per request."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
