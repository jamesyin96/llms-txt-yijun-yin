from dataclasses import dataclass

from app.services.change_detector import ChangeSummary, parse_change_summary, summarize_changes


@dataclass
class PageSnapshot:
    url: str
    canonical_url: str | None = None
    title: str | None = None
    description: str | None = None
    resource_type: str = "html"
    section: str | None = "Key Pages"
    included: bool = True


def test_summarize_changes_counts_added_removed_changed_and_unchanged() -> None:
    previous_pages = [
        PageSnapshot(url="https://example.com/", title="Home"),
        PageSnapshot(url="https://example.com/docs", title="Docs", section="Documentation"),
        PageSnapshot(url="https://example.com/blog", title="Old Blog", section="Articles"),
    ]
    current_pages = [
        PageSnapshot(url="https://example.com/", title="Home"),
        PageSnapshot(url="https://example.com/docs", title="Docs", section="Guides"),
        PageSnapshot(url="https://example.com/pricing", title="Pricing"),
    ]

    summary = summarize_changes(previous_pages, current_pages)

    assert summary == ChangeSummary(added=1, removed=1, changed=1, unchanged=1)


def test_summarize_changes_prefers_canonical_url_as_stable_key() -> None:
    previous_pages = [
        PageSnapshot(
            url="https://example.com/docs?ref=old",
            canonical_url="https://example.com/docs",
            title="Docs",
        )
    ]
    current_pages = [
        PageSnapshot(
            url="https://example.com/docs?ref=new",
            canonical_url="https://example.com/docs",
            title="Docs",
        )
    ]

    summary = summarize_changes(previous_pages, current_pages)

    assert summary == ChangeSummary(unchanged=1)


def test_summarize_changes_ignores_excluded_pages() -> None:
    previous_pages = [
        PageSnapshot(url="https://example.com/", title="Home"),
        PageSnapshot(url="https://example.com/icon.png", resource_type="image", included=False),
    ]
    current_pages = [PageSnapshot(url="https://example.com/", title="Home")]

    summary = summarize_changes(previous_pages, current_pages)

    assert summary == ChangeSummary(unchanged=1)


def test_change_summary_round_trips_json() -> None:
    summary = ChangeSummary(added=2, removed=1, changed=3, unchanged=4)

    parsed = parse_change_summary(summary.to_json())

    assert parsed == summary


def test_parse_change_summary_returns_none_for_invalid_json() -> None:
    assert parse_change_summary("not-json") is None
