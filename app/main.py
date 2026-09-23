from datetime import date as Date, datetime
from contextlib import asynccontextmanager
import secrets
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware
from zoneinfo import ZoneInfo

from .config import get_settings
from .db import init_db, list_publications, list_runs
from .scraper import DouScraper
from .telegram import TelegramPublisher, publish_pending_telegram

settings = get_settings()
scheduler = BackgroundScheduler(timezone=ZoneInfo(settings.timezone))


class ScrapeRequest(BaseModel):
    date: Date | None = None


def run_scheduled_scrape() -> None:
    now = datetime.now(ZoneInfo(settings.timezone))
    DouScraper().scrape(now.date())
    publish_pending_telegram()


def schedule_label() -> str:
    return f"diariamente às {settings.scrape_hour:02d}:{settings.scrape_minute:02d} ({settings.timezone})"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    scheduler.add_job(run_scheduled_scrape, CronTrigger(
        hour=settings.scrape_hour,
        minute=settings.scrape_minute,
        timezone=ZoneInfo(settings.timezone),
    ), id="daily-scrape", replace_existing=True)
    scheduler.start()
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


allowed_hosts = [host.strip() for host in settings.allowed_hosts.split(",") if host.strip()]
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)
if "*" not in allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'; img-src 'self' data:; connect-src 'self'; "
        "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
    )
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "scrape_interval_minutes": settings.scrape_interval_minutes,
            "schedule_hour": settings.scrape_hour, "schedule_minute": settings.scrape_minute,
            "schedule_label": schedule_label(),
            "timezone": settings.timezone,
            "auth_configured": bool(settings.read_api_key and settings.scrape_api_key),
            "telegram_configured": bool(settings.telegram_bot_token and settings.telegram_chat_id)}


@app.get("/api/telegram-link")
def telegram_link() -> dict:
    return {"url": TelegramPublisher().access_url()}


def require_api_key(kind: str):
    def dependency(x_api_key: str | None = Header(default=None)) -> None:
        expected = getattr(settings, f"{kind}_api_key")
        if not expected:
            raise HTTPException(status_code=503, detail="Chave de API não configurada")
        if not x_api_key or not secrets.compare_digest(x_api_key, expected):
            raise HTTPException(status_code=401, detail="X-API-Key inválida ou ausente")
    return dependency


@app.get("/api/laws")
def laws(date: Date | None = Query(default=None), limit: int = Query(default=100, ge=1, le=500),
         _auth: None = Depends(require_api_key("read"))) -> list[dict]:
    return list_publications(date.isoformat() if date else None, limit)


@app.post("/api/scrape")
def scrape(body: ScrapeRequest | None = None, _auth: None = Depends(require_api_key("scrape"))) -> dict:
    target = body.date if body and body.date else datetime.now(ZoneInfo(settings.timezone)).date()
    return execute_scrape(target)


def execute_scrape(target: Date, html: str | None = None) -> dict:
    scraper = DouScraper()
    items = scraper.scrape(target, html=html)
    sent = publish_pending_telegram()
    return {"date": target, "found": len(items), "new": len(scraper.new_items),
            "telegram_sent": sent, "items": items}


@app.post("/api/scrape-html")
def scrape_html(
    date: Date = Query(),
    html: str = Body(media_type="text/html"),
    _auth: None = Depends(require_api_key("scrape")),
) -> dict:
    """Trusted fallback when Render cannot reach the official DOU site."""
    if len(html.encode("utf-8")) > 2_000_000:
        raise HTTPException(status_code=413, detail="Página do DOU muito grande")
    if date.strftime("%d-%m-%Y") not in html or "jsonArray" not in html:
        raise HTTPException(status_code=422, detail="Página do DOU inválida para a data solicitada")
    return execute_scrape(date, html=html)


@app.get("/api/runs")
def runs(limit: int = Query(default=20, ge=1, le=100), _auth: None = Depends(require_api_key("read"))) -> list[dict]:
    return list_runs(limit)


@app.get("/", response_class=HTMLResponse)
def interface() -> str:
    html = Path(__file__).with_name("static").joinpath("index.html").read_text(encoding="utf-8")
    return html.replace("__SCHEDULE__", schedule_label())
