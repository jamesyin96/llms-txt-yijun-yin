from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_scan_endpoint_rejects_localhost() -> None:
    response = client.post("/api/scans", json={"url": "localhost"})

    assert response.status_code == 400
    assert "Localhost" in response.json()["detail"]


def test_scan_endpoint_rejects_private_ip() -> None:
    response = client.post("/api/scans", json={"url": "http://192.168.1.1"})

    assert response.status_code == 400
    assert "Private or local network" in response.json()["detail"]

