import hashlib
import json
import re
from datetime import date
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .config import get_settings
from .db import save_publications, save_run
from .models import Publication

LAW_RE = re.compile(r"\b(Lei|Medida Provisória)\s*(?:n[ºo.]?\s*)?([0-9][\d.]*(?:-[A-Z]{1,3})?)(?:,?\s+de\s+([0-9]{1,2}\s+de\s+\w+\s+de\s+\d{4}))?", re.I)
OFFICIAL_HOSTS = {"in.gov.br", "www.in.gov.br"}


class DouScraper:
    def __init__(self, session: requests.Session | None = None):
        self.settings = get_settings()
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": self.settings.user_agent})
        self.new_items: list[Publication] = []

    def fetch_html(self, target_date: date) -> str:
        params = {"data": target_date.strftime("%d-%m-%Y"), "secao": "dou1"}
        response = self.session.get(self.settings.dou_base_url, params=params,
                                    timeout=self.settings.request_timeout)
        response.raise_for_status()
        return response.text

    def parse(self, html: str, target_date: date) -> list[Publication]:
        soup = BeautifulSoup(html, "html.parser")
        texts: list[tuple[str, str]] = []
        for script in soup.find_all("script"):
            raw = script.string or script.get_text()
            if not raw or "urlTitle" not in raw and "jsonArray" not in raw:
                continue
            try:
                payload = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            self._collect_json(payload, texts)
        if not texts:
            for link in soup.select("a[href]"):
                text = " ".join(link.get_text(" ", strip=True).split())
                if text and LAW_RE.search(text):
                    source_url = self._safe_source_url(link.get("href", ""), self.settings.dou_base_url)
                    if source_url:
                        texts.append((text, source_url))

        publications: list[Publication] = []
        seen: set[str] = set()
        for text, link in texts:
            match = LAW_RE.search(text)
            if not match:
                continue
            kind = "lei" if match.group(1).lower() == "lei" else "medida_provisoria"
            number = match.group(2).replace(".", "")
            title = " ".join(text.split())
            source_url = self._safe_source_url(link, self.settings.dou_base_url)
            if not source_url:
                continue
            fingerprint = hashlib.sha256(f"{target_date}|{kind}|{number}|{title}".encode()).hexdigest()
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            publications.append(Publication(title=title, kind=kind, number=number,
                summary=None, published_date=target_date, source_url=source_url, fingerprint=fingerprint))
        return publications

    @staticmethod
    def _safe_source_url(value: str, base_url: str) -> str | None:
        absolute = urljoin(base_url, value)
        parsed = urlparse(absolute)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or hostname not in OFFICIAL_HOSTS:
            return None
        return absolute

    def _collect_json(self, value, out: list[tuple[str, str]]) -> None:
        if isinstance(value, dict):
            link = value.get("urlTitle") or value.get("url") or value.get("link")
            text = value.get("title") or value.get("ementa") or value.get("texto")
            if isinstance(text, str) and isinstance(link, str):
                source_url = self._safe_source_url(link, "https://www.in.gov.br/en/web/dou/-/")
                if source_url:
                    out.append((text, source_url))
            for child in value.values():
                self._collect_json(child, out)
        elif isinstance(value, list):
            for child in value:
                self._collect_json(child, out)

    def scrape(self, target_date: date, html: str | None = None) -> list[Publication]:
        try:
            items = self.parse(html if html is not None else self.fetch_html(target_date), target_date)
            self.new_items = save_publications(items)
            save_run(target_date.isoformat(), "success", len(self.new_items))
            return items
        except Exception as exc:
            save_run(target_date.isoformat(), "error", 0, str(exc))
            raise
