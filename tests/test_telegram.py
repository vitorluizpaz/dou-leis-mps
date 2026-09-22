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


class FakeChatResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True, "result": {"invite_link": "https://t.me/+convite-seguro"}}


class FakeChatSession:
    def get(self, url, params, timeout):
        return FakeChatResponse()


def test_telegram_publisher_sends_title_and_link():
    settings = get_settings()
    old_token, old_chat = settings.telegram_bot_token, settings.telegram_chat_id
    settings.telegram_bot_token = "bot-token"
    settings.telegram_chat_id = "@channel"
    session = FakeSession()
    try:
        message_id = TelegramPublisher(session).send({
            "title": "LEI <teste>",
            "source_url": "https://www.in.gov.br/en/web/dou/-/lei?a=1&b=2",
        })
        assert message_id == "42"
        assert session.calls[0][1]["chat_id"] == "@channel"
        assert "LEI &lt;teste&gt;" in session.calls[0][1]["text"]
        assert "Clique para ler" in session.calls[0][1]["text"]
    finally:
        settings.telegram_bot_token, settings.telegram_chat_id = old_token, old_chat


def test_telegram_publisher_rejects_non_official_link():
    settings = get_settings()
    old_token, old_chat = settings.telegram_bot_token, settings.telegram_chat_id
    settings.telegram_bot_token = "bot-token"
    settings.telegram_chat_id = "@channel"
    try:
        try:
            TelegramPublisher(FakeSession()).send({
                "title": "LEI de teste",
                "source_url": "https://evil.example/lei",
            })
        except RuntimeError as error:
            assert "domínio oficial" in str(error)
        else:
            raise AssertionError("Link externo deveria ser rejeitado")
    finally:
        settings.telegram_bot_token, settings.telegram_chat_id = old_token, old_chat


def test_telegram_publisher_returns_safe_group_invite():
    settings = get_settings()
    old_token, old_chat, old_url = (
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        settings.telegram_public_url,
    )
    settings.telegram_bot_token = "bot-token"
    settings.telegram_chat_id = "-100123"
    settings.telegram_public_url = ""
    try:
        assert TelegramPublisher(FakeChatSession()).access_url() == "https://t.me/+convite-seguro"
    finally:
        settings.telegram_bot_token = old_token
        settings.telegram_chat_id = old_chat
        settings.telegram_public_url = old_url


def test_telegram_publisher_rejects_unsafe_configured_url():
    settings = get_settings()
    old_url = settings.telegram_public_url
    settings.telegram_public_url = "https://evil.example/convite"
    try:
        assert TelegramPublisher(FakeChatSession()).access_url() is None
    finally:
        settings.telegram_public_url = old_url
