from app.config import get_settings
from app.telegram import TelegramPublisher


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True, "result": {"message_id": 42}}


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append((url, json, timeout))
        return FakeResponse()


def test_telegram_publisher_sends_title_and_link():
    settings = get_settings()
    old_token, old_chat = settings.telegram_bot_token, settings.telegram_chat_id
    settings.telegram_bot_token = "bot-token"
    settings.telegram_chat_id = "@channel"
    session = FakeSession()
    try:
        message_id = TelegramPublisher(session).send({
            "title": "LEI <teste>",
            "source_url": "https://example.com/lei?a=1&b=2",
        })
        assert message_id == "42"
        assert session.calls[0][1]["chat_id"] == "@channel"
        assert "LEI &lt;teste&gt;" in session.calls[0][1]["text"]
        assert "Clique para ler" in session.calls[0][1]["text"]
    finally:
        settings.telegram_bot_token, settings.telegram_chat_id = old_token, old_chat
