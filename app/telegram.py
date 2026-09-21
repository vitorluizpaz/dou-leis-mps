from html import escape
from urllib.parse import urlparse

import requests

from .config import get_settings
from .db import list_pending_telegram, mark_telegram_sent

OFFICIAL_HOSTS = {"in.gov.br", "www.in.gov.br"}


def is_safe_source_url(value: str) -> bool:
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme == "https" and hostname in OFFICIAL_HOSTS


class TelegramPublisher:
    def __init__(self, session: requests.Session | None = None):
        self.settings = get_settings()
        self.session = session or requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    def send(self, item: dict) -> str:
        if not self.configured:
            raise RuntimeError("Telegram não configurado")
        if not is_safe_source_url(item["source_url"]):
            raise RuntimeError("Link da publicação não pertence ao domínio oficial do DOU")
        text = (
            f"<b>{escape(item['title'])}</b>\n\n"
            f"<a href=\"{escape(item['source_url'], quote=True)}\">Clique para ler</a>"
        )
        response = self.session.post(
            f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage",
            json={
                "chat_id": self.settings.telegram_chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=self.settings.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description", "Telegram recusou a mensagem"))
        return str(payload["result"]["message_id"])


def publish_pending_telegram() -> int:
    publisher = TelegramPublisher()
    if not publisher.configured:
        return 0
    sent = 0
    for item in list_pending_telegram():
        message_id = publisher.send(item)
        mark_telegram_sent(item["fingerprint"], message_id)
        sent += 1
    return sent
