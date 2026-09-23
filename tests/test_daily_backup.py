from datetime import date
from unittest.mock import Mock, patch

import requests

from scripts.run_daily import ensure_telegram_ready, fetch_official_html


def test_fetch_official_html_retries_transient_error():
    session = Mock()
    good = Mock(status_code=200, text='{"dateUrl":"23-09-2026","jsonArray":[]}')
    good.raise_for_status.return_value = None
    session.get.side_effect = [requests.exceptions.ReadTimeout(), good]
    with patch("scripts.run_daily.time.sleep"):
        html = fetch_official_html(session, date(2026, 9, 23))
    assert "jsonArray" in html
    assert session.get.call_count == 2
    assert session.get.call_args.kwargs["params"] == {"data": "23-09-2026", "secao": "dou1"}


def test_telegram_readiness_detects_restricted_bot():
    session = Mock()
    response = Mock()
    response.json.return_value = {
        "chat_type": "supergroup", "bot_status": "restricted",
        "members_can_send_messages": False, "bot_can_send_messages": False,
    }
    session.get.return_value = response
    try:
        ensure_telegram_ready(session, "https://example.com", {"X-API-Key": "test"})
    except RuntimeError as error:
        assert "sem permissão" in str(error)
    else:
        raise AssertionError("Bot restrito deveria reprovar a rotina")


def test_telegram_readiness_accepts_admin_in_supergroup():
    session = Mock()
    response = Mock()
    response.json.return_value = {
        "chat_type": "supergroup", "bot_status": "administrator",
        "members_can_send_messages": False, "bot_can_send_messages": None,
    }
    session.get.return_value = response
    ensure_telegram_ready(session, "https://example.com", {"X-API-Key": "test"})
    assert session.get.call_args.args[0] == "https://example.com/api/telegram-diagnostics"
