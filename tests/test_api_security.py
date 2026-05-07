from fastapi.testclient import TestClient
from uuid import uuid4

from app.db import init_db
from app.main import app


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
