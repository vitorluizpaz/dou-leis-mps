"""GitHub Actions backup: scrape on Render, or fetch DOU from the runner."""

import os
import sys
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests


DOU_URL = "https://www.in.gov.br/leiturajornal"


def fetch_official_html(session: requests.Session, target_date: date) -> str:
    query_date = target_date.strftime("%d-%m-%Y")
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            response = session.get(
                DOU_URL,
                params={"data": query_date, "secao": "dou1"},
                headers={"User-Agent": "DOU-LeisMPs/0.1"},
                timeout=(15, 45),
            )
            response.raise_for_status()
            if query_date not in response.text or "jsonArray" not in response.text:
                raise ValueError("Resposta do DOU não contém a edição esperada")
            return response.text
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(min(2 ** attempt, 10))
    raise RuntimeError("Não foi possível obter a edição oficial do DOU") from last_error


def report(response: requests.Response) -> None:
    response.raise_for_status()
    data = response.json()
    print(
        f"Data: {data['date']}; encontrados: {data['found']}; "
        f"novos: {data['new']}; enviados ao Telegram: {data['telegram_sent']}"
    )


def ensure_telegram_ready(session: requests.Session, api_url: str, headers: dict) -> None:
    response = session.get(
        f"{api_url}/api/telegram-diagnostics",
        headers=headers,
        timeout=(15, 30),
    )
    response.raise_for_status()
    rights = response.json()
    status = rights.get("bot_status")
    chat_type = rights.get("chat_type")
    if status in {"creator", "administrator"}:
        allowed = chat_type != "channel" or rights.get("bot_can_post_messages") is True
    elif status == "restricted":
        allowed = rights.get("bot_can_send_messages") is True
    elif status == "member":
        allowed = chat_type != "channel" and rights.get("members_can_send_messages") is not False
    else:
        allowed = False
    if not allowed:
        raise RuntimeError(f"Bot sem permissão para publicar no Telegram: {rights}")


def main() -> None:
    api_url = os.environ["API_URL"].rstrip("/")
    key = os.environ["SCRAPE_API_KEY"]
    if not api_url.startswith("https://") or not key:
        raise RuntimeError("API_URL HTTPS e SCRAPE_API_KEY são obrigatórios")
    target_date = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    date_text = target_date.isoformat()
    headers = {"X-API-Key": key}
    with requests.Session() as session:
        try:
            response = session.post(
                f"{api_url}/api/scrape",
                json={"date": date_text},
                headers=headers,
                timeout=(30, 180),
            )
            report(response)
        except (requests.RequestException, ValueError, KeyError) as exc:
            print(f"Coleta direta falhou ({type(exc).__name__}); tentando via runner.", file=sys.stderr)
        else:
            ensure_telegram_ready(session, api_url, headers)
            return

        html = fetch_official_html(session, target_date)
        response = session.post(
            f"{api_url}/api/scrape-html",
            params={"date": date_text},
            data=html.encode("utf-8"),
            headers={**headers, "Content-Type": "text/html; charset=utf-8"},
            timeout=(30, 180),
        )
        try:
            report(response)
            ensure_telegram_ready(session, api_url, headers)
        except (requests.RequestException, ValueError, KeyError):
            try:
                diagnostics = session.get(
                    f"{api_url}/api/telegram-diagnostics",
                    headers=headers,
                    timeout=(15, 30),
                )
                if diagnostics.ok:
                    print(f"Permissões do bot: {diagnostics.json()}", file=sys.stderr)
            except (requests.RequestException, ValueError):
                pass
            raise


if __name__ == "__main__":
    main()
