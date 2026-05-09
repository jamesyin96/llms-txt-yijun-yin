"""Metadata-based change detection between scan versions.

V1 compares the included page/resource records we already store. It does not
fetch pages again or inspect full body text here; the scanner calls this after
the crawler has produced the latest metadata snapshot.
"""

from dataclasses import asdict, dataclass
import json
from typing import Any


TRACKED_FIELDS = ("title", "description", "resource_type", "section")


@dataclass(frozen=True)
class ChangeSummary:
    """Compact counts for what changed between two scan snapshots."""

    added: int = 0
    removed: int = 0
    changed: int = 0
    unchanged: int = 0

    def to_json(self) -> str:
        """Serialize the summary for storage on the Scan row."""

        return json.dumps(asdict(self), sort_keys=True)


def summarize_changes(previous_pages: list[Any], current_pages: list[Any]) -> ChangeSummary:
    """Compare two page snapshots and return added/removed/changed counts.

    Pages are matched by canonical URL when present, otherwise by URL. A page is
    considered changed when its title, description, resource type, or section
    differs from the previous completed scan.
    """

    previous_by_key = _pages_by_key(previous_pages)
    current_by_key = _pages_by_key(current_pages)

    previous_keys = set(previous_by_key)
    current_keys = set(current_by_key)
    shared_keys = previous_keys & current_keys

    changed = sum(
        _page_signature(previous_by_key[key]) != _page_signature(current_by_key[key])
        for key in shared_keys
    )

    return ChangeSummary(
        added=len(current_keys - previous_keys),
        removed=len(previous_keys - current_keys),
        changed=changed,
        unchanged=len(shared_keys) - changed,
    )


def parse_change_summary(value: str | None) -> ChangeSummary | None:
    """Parse a stored change summary, returning None for empty/invalid data."""

    if not value:
        return None

    try:
        raw = json.loads(value)
    except json.JSONDecodeError:
        return None

    if not isinstance(raw, dict):
        return None

    return ChangeSummary(
        added=_int_value(raw.get("added")),
        removed=_int_value(raw.get("removed")),
        changed=_int_value(raw.get("changed")),
        unchanged=_int_value(raw.get("unchanged")),
    )


def _pages_by_key(pages: list[Any]) -> dict[str, Any]:
    by_key = {}
    for page in pages:
        if not getattr(page, "included", True):
            continue
        key = _page_key(page)
        if key:
            by_key[key] = page
    return by_key


def _page_key(page: Any) -> str:
    return _normalized_value(getattr(page, "canonical_url", None) or getattr(page, "url", None))


def _page_signature(page: Any) -> tuple[str, ...]:
    return tuple(_normalized_value(getattr(page, field, None)) for field in TRACKED_FIELDS)


def _normalized_value(value: Any) -> str:
    return str(value or "").strip()


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
