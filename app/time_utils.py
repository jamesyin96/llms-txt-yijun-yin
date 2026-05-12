"""UTC datetime helpers shared by persistence, API, and scheduler code."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""

    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """Treat older naive datetimes as UTC and return timezone-aware UTC."""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
