from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from uuid import uuid4

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Scan
from app.services.change_detector import ChangeSummary
from app.time_utils import utc_now


init_db()
client = TestClient(app)


def test_scan_endpoint_rejects_localhost() -> None:
    response = client.post("/api/scans", json={"url": "localhost"})

    assert response.status_code == 400
    assert "Localhost" in response.json()["detail"]


def test_scan_endpoint_rejects_private_ip() -> None:
    response = client.post("/api/scans", json={"url": "http://192.168.1.1"})

    assert response.status_code == 400
    assert "Private or local network" in response.json()["detail"]


def test_scan_endpoint_assigns_per_site_version_numbers(monkeypatch) -> None:
    import app.main as main

    monkeypatch.setattr(main, "run_scan", lambda scan_id: None)
    primary_url = f"https://version-{uuid4().hex}.example.com/"
    other_url = f"https://version-{uuid4().hex}.example.com/"

    first = client.post("/api/scans", json={"url": primary_url})
    other_site = client.post("/api/scans", json={"url": other_url})
    second = client.post("/api/scans", json={"url": primary_url})

    assert first.status_code == 200
    assert other_site.status_code == 200
    assert second.status_code == 200
    assert first.json()["version_number"] == 1
    assert other_site.json()["version_number"] == 1
    assert second.json()["version_number"] == 2


def test_scan_status_includes_version_number(monkeypatch) -> None:
    import app.main as main

    monkeypatch.setattr(main, "run_scan", lambda scan_id: None)
    created = client.post(
        "/api/scans",
        json={"url": f"https://version-status-{uuid4().hex}.example.com/"},
    )
    scan_id = created.json()["scan_id"]

    response = client.get(f"/api/scans/{scan_id}")

    assert response.status_code == 200
    assert response.json()["version_number"] == created.json()["version_number"]


def test_scan_endpoint_accepts_advanced_crawl_settings(monkeypatch) -> None:
    import app.main as main

    monkeypatch.setattr(main, "run_scan", lambda scan_id: None)
    response = client.post(
        "/api/scans",
        json={
            "url": f"https://advanced-{uuid4().hex}.example.com/",
            "crawl_max_pages": 25,
            "crawl_max_depth": 1,
            "crawl_max_duration_seconds": 12,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["crawl_max_pages"] == 25
    assert data["crawl_max_depth"] == 1
    assert data["crawl_max_duration_seconds"] == 12

    status = client.get(f"/api/scans/{data['scan_id']}")
    assert status.status_code == 200
    assert status.json()["crawl_max_pages"] == 25
    assert status.json()["crawl_max_depth"] == 1
    assert status.json()["crawl_max_duration_seconds"] == 12


def test_scan_endpoint_rejects_out_of_range_crawl_settings(monkeypatch) -> None:
    import app.main as main

    monkeypatch.setattr(main, "run_scan", lambda scan_id: None)
    response = client.post(
        "/api/scans",
        json={
            "url": f"https://advanced-invalid-{uuid4().hex}.example.com/",
            "crawl_max_pages": 0,
            "crawl_max_depth": 6,
            "crawl_max_duration_seconds": 61,
        },
    )

    assert response.status_code == 422


def test_scan_history_lists_versions_for_one_site(monkeypatch) -> None:
    import app.main as main

    monkeypatch.setattr(main, "run_scan", lambda scan_id: None)
    primary_url = f"https://history-{uuid4().hex}.example.com/"
    other_url = f"https://history-{uuid4().hex}.example.com/"

    first = client.post("/api/scans", json={"url": primary_url})
    client.post("/api/scans", json={"url": other_url})
    second = client.post("/api/scans", json={"url": primary_url})

    response = client.get("/api/scans", params={"url": primary_url})

    assert response.status_code == 200
    data = response.json()
    assert data["root_url"] == primary_url
    assert [scan["scan_id"] for scan in data["scans"]] == [
        second.json()["scan_id"],
        first.json()["scan_id"],
    ]
    assert [scan["version_number"] for scan in data["scans"]] == [2, 1]


def test_scan_history_serializes_created_at_in_utc(monkeypatch) -> None:
    import app.main as main

    monkeypatch.setattr(main, "run_scan", lambda scan_id: None)
    url = f"https://history-time-{uuid4().hex}.example.com/"
    created = client.post("/api/scans", json={"url": url})
    scan_id = created.json()["scan_id"]

    db = SessionLocal()
    try:
        scan = db.get(Scan, scan_id)
        assert scan is not None
        scan.created_at = datetime(2026, 5, 12, 1, 48, 15)
        db.commit()
    finally:
        db.close()

    response = client.get("/api/scans", params={"url": url})

    assert response.status_code == 200
    assert response.json()["scans"][0]["created_at"].endswith("Z")


def test_scan_history_includes_download_url_for_completed_versions(monkeypatch) -> None:
    import app.main as main

    monkeypatch.setattr(main, "run_scan", lambda scan_id: None)
    url = f"https://history-complete-{uuid4().hex}.example.com/"
    created = client.post("/api/scans", json={"url": url})
    scan_id = created.json()["scan_id"]

    db = SessionLocal()
    try:
        scan = db.get(Scan, scan_id)
        assert scan is not None
        scan.status = "complete"
        scan.previous_scan_id = scan_id - 1
        scan.change_summary = ChangeSummary(added=2, removed=1, changed=3, unchanged=4).to_json()
        scan.output_path = f"scan-{scan.id}-v{scan.version_number}-llms.txt"
        db.commit()
    finally:
        db.close()

    response = client.get("/api/scans", params={"url": url})

    assert response.status_code == 200
    assert response.json()["scans"][0]["download_url"] == f"/download/{scan_id}"
    assert response.json()["scans"][0]["previous_scan_id"] == scan_id - 1
    assert response.json()["scans"][0]["change_summary"] == {
        "added": 2,
        "removed": 1,
        "changed": 3,
        "unchanged": 4,
    }


def test_scan_history_rejects_unsafe_url() -> None:
    response = client.get("/api/scans", params={"url": "localhost"})

    assert response.status_code == 400
    assert "Localhost" in response.json()["detail"]


def test_scan_endpoint_reuses_recent_completed_scan_and_sets_flag(monkeypatch) -> None:
    import app.main as main

    monkeypatch.setattr(main, "run_scan", lambda scan_id: None)
    url = f"https://reuse-{uuid4().hex}.example.com/"
    created = client.post("/api/scans", json={"url": url})
    scan_id = created.json()["scan_id"]

    db = SessionLocal()
    try:
        scan = db.get(Scan, scan_id)
        assert scan is not None
        scan.status = "complete"
        scan.created_at = utc_now()
        db.commit()
    finally:
        db.close()

    reused = client.post("/api/scans", json={"url": url, "auto_refresh_daily": True})

    assert reused.status_code == 200
    payload = reused.json()
    assert payload["scan_id"] == scan_id
    assert payload["reused_existing"] is True
    assert payload["auto_refresh_daily"] is True


def test_scan_endpoint_creates_new_scan_when_last_completed_is_stale(monkeypatch) -> None:
    import app.main as main

    monkeypatch.setattr(main, "run_scan", lambda scan_id: None)
    url = f"https://stale-{uuid4().hex}.example.com/"
    first = client.post("/api/scans", json={"url": url})
    first_id = first.json()["scan_id"]

    db = SessionLocal()
    try:
        scan = db.get(Scan, first_id)
        assert scan is not None
        scan.status = "complete"
        scan.created_at = utc_now() - timedelta(hours=13)
        db.commit()
    finally:
        db.close()

    second = client.post("/api/scans", json={"url": url})

    assert second.status_code == 200
    data = second.json()
    assert data["scan_id"] != first_id
    assert data["version_number"] == 2
    assert data["reused_existing"] is False


def test_scan_history_returns_most_recent_ten_versions(monkeypatch) -> None:
    import app.main as main

    monkeypatch.setattr(main, "run_scan", lambda scan_id: None)
    url = f"https://history-ten-{uuid4().hex}.example.com/"

    scan_ids: list[int] = []
    for _ in range(12):
        created = client.post("/api/scans", json={"url": url})
        scan_ids.append(created.json()["scan_id"])

    response = client.get("/api/scans", params={"url": url})

    assert response.status_code == 200
    scans = response.json()["scans"]
    assert len(scans) == 10
    assert scans[0]["scan_id"] == scan_ids[-1]
    assert scans[-1]["scan_id"] == scan_ids[-10]


def test_auto_refresh_status_endpoint_returns_scheduler_health() -> None:
    response = client.get("/api/auto-refresh/status")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["lookback_hours"] == 12
    assert data["poll_interval_seconds"] == 3600
    assert data["last_queued_count"] >= 0
