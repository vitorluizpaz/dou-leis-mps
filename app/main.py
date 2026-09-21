from datetime import date as Date, datetime
from contextlib import asynccontextmanager
import secrets
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from zoneinfo import ZoneInfo

from .config import get_settings
from .db import init_db, list_publications, list_runs
from .scraper import DouScraper
from .telegram import publish_pending_telegram

settings = get_settings()
scheduler = BackgroundScheduler(timezone=ZoneInfo(settings.timezone))


class ScrapeRequest(BaseModel):
    date: Date | None = None


def run_scheduled_scrape() -> None:
    now = datetime.now(ZoneInfo(settings.timezone))
    DouScraper().scrape(now.date())
    publish_pending_telegram()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    scheduler.add_job(run_scheduled_scrape, IntervalTrigger(minutes=settings.scrape_interval_minutes,
        timezone=ZoneInfo(settings.timezone)), id="hourly-scrape", replace_existing=True)
    scheduler.start()
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "scrape_interval_minutes": settings.scrape_interval_minutes,
            "timezone": settings.timezone,
            "auth_configured": bool(settings.read_api_key and settings.scrape_api_key),
            "telegram_configured": bool(settings.telegram_bot_token and settings.telegram_chat_id)}


def require_api_key(kind: str):
    def dependency(x_api_key: str | None = Header(default=None)) -> None:
        expected = getattr(settings, f"{kind}_api_key")
        if not expected:
            raise HTTPException(status_code=503, detail="Chave de API não configurada")
        if not x_api_key or not secrets.compare_digest(x_api_key, expected):
            raise HTTPException(status_code=401, detail="X-API-Key inválida ou ausente")
    return dependency


@app.get("/api/laws")
def laws(date: str | None = Query(default=None), limit: int = Query(default=100, le=500),
         _auth: None = Depends(require_api_key("read"))) -> list[dict]:
    return list_publications(date, limit)


@app.post("/api/scrape")
def scrape(body: ScrapeRequest | None = None, _auth: None = Depends(require_api_key("scrape"))) -> dict:
    target = body.date if body and body.date else datetime.now(ZoneInfo(settings.timezone)).date()
    scraper = DouScraper()
    items = scraper.scrape(target)
    sent = publish_pending_telegram()
    return {"date": target, "found": len(items), "new": len(scraper.new_items),
            "telegram_sent": sent, "items": items}


@app.get("/api/runs")
def runs(limit: int = Query(default=20, le=100), _auth: None = Depends(require_api_key("read"))) -> list[dict]:
    return list_runs(limit)


@app.get("/", response_class=HTMLResponse)
def interface() -> str:
    html = Path(__file__).with_name("static").joinpath("index.html").read_text(encoding="utf-8")
    return html.replace("__SCHEDULE__", f"a cada {settings.scrape_interval_minutes} minutos ({settings.timezone})")
