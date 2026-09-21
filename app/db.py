from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, create_engine, desc, insert, select, text
from sqlalchemy.exc import IntegrityError

from .config import get_settings
from .models import Publication

settings = get_settings()
database_url = settings.database_url
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

if database_url.startswith("sqlite"):
    Path("data").mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
else:
    engine = create_engine(database_url, pool_pre_ping=True)

metadata = MetaData()
publications = Table(
    "publications", metadata,
    Column("id", Integer, primary_key=True), Column("title", Text, nullable=False),
    Column("kind", String(40), nullable=False), Column("number", String(80)),
    Column("summary", Text), Column("published_date", String(10), nullable=False),
    Column("source_url", Text, nullable=False), Column("fingerprint", String(64), nullable=False, unique=True),
    Column("created_at", DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False),
)
scrape_runs = Table(
    "scrape_runs", metadata,
    Column("id", Integer, primary_key=True), Column("requested_date", String(10), nullable=False),
    Column("started_at", DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False),
    Column("status", String(20), nullable=False), Column("found", Integer, nullable=False, default=0), Column("error", Text),
)
telegram_deliveries = Table(
    "telegram_deliveries", metadata,
    Column("id", Integer, primary_key=True), Column("fingerprint", String(64), nullable=False, unique=True),
    Column("message_id", String(80), nullable=False),
    Column("sent_at", DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False),
)


def init_db() -> None:
    metadata.create_all(engine)


@contextmanager
def connect():
    with engine.begin() as connection:
        yield connection


def save_publications(items: list[Publication]) -> list[Publication]:
    inserted: list[Publication] = []
    for item in items:
        try:
            with connect() as connection:
                connection.execute(insert(publications).values(
                    title=item.title, kind=item.kind, number=item.number, summary=item.summary,
                    published_date=item.published_date.isoformat(), source_url=item.source_url,
                    fingerprint=item.fingerprint))
            inserted.append(item)
        except IntegrityError:
            pass
    return inserted


def list_pending_telegram(limit: int = 100) -> list[dict]:
    query = (select(publications)
        .outerjoin(telegram_deliveries, publications.c.fingerprint == telegram_deliveries.c.fingerprint)
        .where(telegram_deliveries.c.id.is_(None))
        .order_by(publications.c.published_date, publications.c.id)
        .limit(limit))
    with engine.connect() as connection:
        return [dict(row._mapping) for row in connection.execute(query).fetchall()]


def mark_telegram_sent(fingerprint: str, message_id: str) -> None:
    try:
        with connect() as connection:
            connection.execute(insert(telegram_deliveries).values(
                fingerprint=fingerprint, message_id=message_id))
    except IntegrityError:
        pass


def list_publications(published_date: str | None = None, limit: int = 100) -> list[dict]:
    query = select(publications).order_by(desc(publications.c.published_date), desc(publications.c.id)).limit(limit)
    if published_date:
        query = query.where(publications.c.published_date == published_date)
    with engine.connect() as connection:
        return [dict(row._mapping) for row in connection.execute(query).fetchall()]


def save_run(requested_date: str, status: str, found: int = 0, error: str | None = None) -> None:
    with connect() as connection:
        connection.execute(insert(scrape_runs).values(requested_date=requested_date, status=status, found=found, error=error))


def list_runs(limit: int = 20) -> list[dict]:
    query = select(scrape_runs).order_by(desc(scrape_runs.c.id)).limit(limit)
    with engine.connect() as connection:
        return [dict(row._mapping) for row in connection.execute(query).fetchall()]
