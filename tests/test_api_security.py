from fastapi.testclient import TestClient
from uuid import uuid4

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Scan
from app.services.change_detector import ChangeSummary


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
