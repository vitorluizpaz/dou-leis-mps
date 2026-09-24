from datetime import date, datetime

from fastapi.testclient import TestClient
import pytest

from app.main import app, settings
import app.main as main_module


def test_api_lifecycle_and_read_endpoints():
    settings.read_api_key = "read-key"
    settings.scrape_api_key = "scrape-key"
    with TestClient(app, base_url="http://localhost") as client:
        health = client.get("/api/health").json()
        assert health["status"] == "ok"
        assert health["schedule_hour"] == settings.scrape_hour
        assert health["schedule_minute"] == settings.scrape_minute
        assert "diariamente às" in health["schedule_label"]
        assert isinstance(health["recent_checks"], list)
        assert all(set(run) == {"date", "at", "status", "found"} for run in health["recent_checks"])
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


def test_scrape_html_requires_key_and_valid_edition(monkeypatch):
    settings.scrape_api_key = "scrape-key"
    called = []

    def fake_execute(target, html=None):
        called.append((target.isoformat(), html))
        return {"date": target.isoformat(), "found": 0, "new": 0,
                "telegram_sent": 0, "items": []}

    monkeypatch.setattr(main_module, "execute_scrape", fake_execute)
    html = '<html><script type="application/json">{"dateUrl":"23-09-2026","jsonArray":[]}</script></html>'
    with TestClient(app, base_url="http://localhost") as client:
        endpoint = "/api/scrape-html?date=2026-09-23"
        assert client.post(endpoint, content=html, headers={"Content-Type": "text/html"}).status_code == 401
        headers = {"X-API-Key": "scrape-key", "Content-Type": "text/html"}
        assert client.post(endpoint, content="erro", headers=headers).status_code == 422
        assert client.post(endpoint, content="x" * 2_000_001, headers=headers).status_code == 413
        response = client.post(endpoint, content=html, headers=headers)
        assert response.status_code == 200
        assert called == [("2026-09-23", html)]


def test_telegram_diagnostics_is_protected(monkeypatch):
    settings.scrape_api_key = "scrape-key"
    monkeypatch.setattr(main_module.TelegramPublisher, "diagnose", lambda self: {"bot_status": "member"})
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/api/telegram-diagnostics").status_code == 401
        response = client.get("/api/telegram-diagnostics", headers={"X-API-Key": "scrape-key"})
        assert response.status_code == 200
        assert response.json() == {"bot_status": "member"}


def test_health_reports_database_unavailable(monkeypatch):
    monkeypatch.setattr(main_module, "database_ready", lambda: False)
    with TestClient(app, base_url="http://localhost") as client:
        response = client.get("/api/health")
        assert response.status_code == 503
        assert response.json() == {"detail": "Banco de dados indisponível"}


def test_health_exposes_only_safe_run_summary(monkeypatch):
    monkeypatch.setattr(main_module, "database_ready", lambda: True)
    monkeypatch.setattr(main_module, "list_runs", lambda limit: [{
        "requested_date": "2026-09-24", "started_at": datetime(2026, 9, 24, 13),
        "status": "delivery_error", "found": 2, "error": "private detail",
    }])
    with TestClient(app, base_url="http://localhost") as client:
        checks = client.get("/api/health").json()["recent_checks"]
    assert checks == [{"date": "2026-09-24", "at": "2026-09-24T13:00:00",
                       "status": "delivery_error", "found": 2}]


def test_delivery_failure_is_recorded(monkeypatch):
    class FakeScraper:
        new_items = []

        def scrape(self, target, html=None):
            return [object()]

    recorded = []
    monkeypatch.setattr(main_module, "DouScraper", FakeScraper)
    monkeypatch.setattr(main_module, "publish_pending_telegram", lambda: (_ for _ in ()).throw(RuntimeError("Telegram offline")))
    monkeypatch.setattr(main_module, "save_run", lambda *args: recorded.append(args))
    with pytest.raises(RuntimeError, match="Telegram offline"):
        main_module.execute_scrape(date(2026, 9, 24))
    assert recorded == [("2026-09-24", "delivery_error", 1)]
