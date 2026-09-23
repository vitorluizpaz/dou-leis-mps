from sqlalchemy import create_engine, insert, select

from app.db import metadata, publications, scrape_runs, telegram_deliveries
from scripts.migrate_database import migrate


def test_migration_preserves_publications_runs_and_delivery_ids():
    source = create_engine("sqlite:///:memory:")
    destination = create_engine("sqlite:///:memory:")
    metadata.create_all(source)
    fingerprint = "a" * 64
    with source.begin() as connection:
        connection.execute(insert(publications).values(
            id=7, title="LEI Nº 1", kind="lei", number="1", summary=None,
            published_date="2026-09-23", source_url="https://www.in.gov.br/teste",
            fingerprint=fingerprint,
        ))
        connection.execute(insert(scrape_runs).values(
            id=3, requested_date="2026-09-23", status="success", found=1,
        ))
        connection.execute(insert(telegram_deliveries).values(
            id=2, fingerprint=fingerprint, message_id="123",
        ))

    counts = migrate(source, destination)
    assert counts == {"publications": 1, "scrape_runs": 1, "telegram_deliveries": 1}
    with destination.connect() as connection:
        assert connection.execute(select(publications.c.id)).scalar_one() == 7
        assert connection.execute(select(telegram_deliveries.c.message_id)).scalar_one() == "123"

    try:
        migrate(source, destination)
    except ValueError as error:
        assert "já contém dados" in str(error)
    else:
        raise AssertionError("Migração repetida deveria ser recusada")
