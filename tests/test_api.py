from fastapi.testclient import TestClient

from app.main import app, settings


def test_api_lifecycle_and_read_endpoints():
    settings.read_api_key = "read-key"
    settings.scrape_api_key = "scrape-key"
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/api/laws?date=2026-09-20").status_code == 401
        assert client.get("/api/laws?date=2026-09-20", headers={"X-API-Key": "read-key"}).status_code == 200
        assert client.get("/api/runs").status_code == 401
        assert client.get("/api/runs", headers={"X-API-Key": "read-key"}).status_code == 200
        assert client.get("/").status_code == 200
