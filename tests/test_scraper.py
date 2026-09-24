from datetime import date

from app.config import get_settings
from app.scraper import DouScraper


FIXTURE = '''<html><script type="application/json">{"jsonArray":[
{"title":"LEI Nº 15.001, DE 20 DE SETEMBRO DE 2026 — Institui a política nacional.","urlTitle":"lei-n-15-001-de-20-de-setembro-de-2026"},
{"title":"MEDIDA PROVISÓRIA Nº 1.301, DE 20 DE SETEMBRO DE 2026", "urlTitle":"medida-provisoria-n-1-301"},
{"title":"DECRETO Nº 1.000, DE 20 DE SETEMBRO DE 2026", "urlTitle":"decreto-n-1"}]}</script></html>'''


def test_parse_only_laws_and_mps():
    items = DouScraper().parse(FIXTURE, date(2026, 9, 20))
    assert len(items) == 2
    assert {item.kind for item in items} == {"lei", "medida_provisoria"}
    assert items[0].source_url.startswith("https://www.in.gov.br/en/web/dou/-/")


def test_parse_deduplicates_items():
    scraper = DouScraper()
    html = FIXTURE.replace('</script>', '</script><script type="application/json">' + FIXTURE.split('<script type="application/json">',1)[1].split('</script>',1)[0] + '</script>')
    assert len(scraper.parse(html, date(2026, 9, 20))) == 2


def test_parse_discards_non_official_links():
    html = '''<html><a href="https://evil.example/lei">LEI Nº 15.001, DE 20 DE SETEMBRO DE 2026</a></html>'''
    assert DouScraper().parse(html, date(2026, 9, 20)) == []


def test_scrape_records_total_found_not_only_new(monkeypatch):
    import app.scraper as scraper_module

    recorded = []
    monkeypatch.setattr(scraper_module, "save_publications", lambda items: [])
    monkeypatch.setattr(scraper_module, "save_run", lambda *args: recorded.append(args))
    scraper = DouScraper()
    assert len(scraper.scrape(date(2026, 9, 20), html=FIXTURE)) == 2
    assert recorded == [("2026-09-20", "success", 2)]
