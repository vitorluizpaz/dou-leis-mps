import hashlib
import json
import re
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .config import get_settings
from .db import save_publications, save_run
from .models import Publication

LAW_RE = re.compile(r"\b(Lei|Medida Provisória)\s*(?:n[ºo.]?\s*)?([0-9][\d.]*(?:-[A-Z]{1,3})?)(?:,?\s+de\s+([0-9]{1,2}\s+de\s+\w+\s+de\s+\d{4}))?", re.I)


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
                    texts.append((text, urljoin(self.settings.dou_base_url, link.get("href", ""))))

        publications: list[Publication] = []
        seen: set[str] = set()
        for text, link in texts:
            match = LAW_RE.search(text)
            if not match:
                continue
            kind = "lei" if match.group(1).lower() == "lei" else "medida_provisoria"
            number = match.group(2).replace(".", "")
            title = " ".join(text.split())
            fingerprint = hashlib.sha256(f"{target_date}|{kind}|{number}|{title}".encode()).hexdigest()
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            publications.append(Publication(title=title, kind=kind, number=number,
                summary=None, published_date=target_date, source_url=link, fingerprint=fingerprint))
        return publications

    def _collect_json(self, value, out: list[tuple[str, str]]) -> None:
        if isinstance(value, dict):
            link = value.get("urlTitle") or value.get("url") or value.get("link")
            text = value.get("title") or value.get("ementa") or value.get("texto")
            if isinstance(text, str) and isinstance(link, str):
                out.append((text, urljoin("https://www.in.gov.br/en/web/dou/-/", link) if not link.startswith("http") else link))
            for child in value.values():
                self._collect_json(child, out)
        elif isinstance(value, list):
            for child in value:
                self._collect_json(child, out)

    def scrape(self, target_date: date) -> list[Publication]:
        try:
            items = self.parse(self.fetch_html(target_date), target_date)
            self.new_items = save_publications(items)
            save_run(target_date.isoformat(), "success", len(self.new_items))
            return items
        except Exception as exc:
            save_run(target_date.isoformat(), "error", 0, str(exc))
            raise
