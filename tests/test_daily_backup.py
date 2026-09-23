from datetime import date
from unittest.mock import Mock, patch

import requests

from scripts.run_daily import fetch_official_html


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
