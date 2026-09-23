"""Copy the bot's PostgreSQL data to another PostgreSQL database.

The source is read-only. The destination must not contain bot data; all copies
and verification occur in one destination transaction.
"""

import os
import sys

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine

from app.db import metadata, publications, scrape_runs, telegram_deliveries

TABLES = (publications, scrape_runs, telegram_deliveries)


def migrate(source: Engine, destination: Engine) -> dict[str, int]:
    if source is destination:
        raise ValueError("Origem e destino não podem ser o mesmo banco")

    counts: dict[str, int] = {}
    with source.connect() as source_connection, destination.begin() as target_connection:
        metadata.create_all(target_connection)
        for table in TABLES:
            current = target_connection.execute(select(func.count()).select_from(table)).scalar_one()
            if current:
                raise ValueError("O banco de destino já contém dados do bot")

        for table in TABLES:
            rows = [dict(row) for row in source_connection.execute(select(table)).mappings()]
            if rows:
                target_connection.execute(table.insert(), rows)
            copied = [dict(row) for row in target_connection.execute(select(table)).mappings()]
            if copied != rows:
                raise RuntimeError(f"Verificação da tabela {table.name} falhou")
            counts[table.name] = len(rows)

            if destination.dialect.name == "postgresql" and rows:
                # Explicit IDs do not advance PostgreSQL's serial sequence.
                target_connection.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                    f"(SELECT MAX(id) FROM {table.name}))"
                ))
    return counts


def main() -> None:
    source_url = os.getenv("SOURCE_DATABASE_URL", "")
    target_url = os.getenv("TARGET_DATABASE_URL", "")
    if not source_url or not target_url:
        raise SystemExit("Defina SOURCE_DATABASE_URL e TARGET_DATABASE_URL no ambiente")
    if source_url == target_url:
        raise SystemExit("Origem e destino não podem ser o mesmo banco")
    if not source_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
        raise SystemExit("A origem deve ser PostgreSQL")
    if not target_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
        raise SystemExit("O destino deve ser PostgreSQL")

    def normalize(url: str) -> str:
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    source = create_engine(normalize(source_url), pool_pre_ping=True)
    destination = create_engine(normalize(target_url), pool_pre_ping=True)
    try:
        counts = migrate(source, destination)
    except Exception as exc:
        # Connection exceptions can contain URLs or passwords. Never print them.
        print(f"Migração falhou ({type(exc).__name__}); banco de origem preservado.", file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        source.dispose()
        destination.dispose()
    print("Migração verificada: " + ", ".join(f"{name}={count}" for name, count in counts.items()))


if __name__ == "__main__":
    main()
