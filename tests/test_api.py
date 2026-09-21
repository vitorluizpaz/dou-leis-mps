from fastapi.testclient import TestClient

from app.main import app, settings


def test_api_lifecycle_and_read_endpoints():
    settings.read_api_key = "read-key"
    settings.scrape_api_key = "scrape-key"
    with TestClient(app, base_url="http://localhost") as client:
        health = client.get("/api/health").json()
        assert health["status"] == "ok"
        assert health["schedule_hour"] == settings.scrape_hour
        assert health["schedule_minute"] == settings.scrape_minute
        assert "diariamente às" in health["schedule_label"]
        assert client.get("/api/laws?date=2026-09-20").status_code == 401
        assert client.get("/api/laws?date=2026-09-20", headers={"X-API-Key": "read-key"}).status_code == 200
        assert client.get("/api/runs").status_code == 401
        assert client.get("/api/runs", headers={"X-API-Key": "read-key"}).status_code == 200
        assert client.get("/api/laws?date=not-a-date", headers={"X-API-Key": "read-key"}).status_code == 422
        assert client.get("/api/laws?limit=0", headers={"X-API-Key": "read-key"}).status_code == 422
        assert client.get("/docs").status_code == 404
        assert client.get("/").headers["x-content-type-options"] == "nosniff"
        assert client.get("/").headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]
        assert client.get("/").status_code == 200
