from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DOU Leis e MPs"
    database_url: str = "sqlite:///data/dou.sqlite3"
    dou_base_url: str = "https://www.in.gov.br/leiturajornal"
    allowed_hosts: str = "dou-leis-mps.onrender.com,localhost,127.0.0.1"
    timezone: str = "America/Sao_Paulo"
    scrape_interval_minutes: int = 1440
    scrape_hour: int = 9
    scrape_minute: int = 55
    enable_docs: bool = False
    read_api_key: str = ""
    scrape_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_public_url: str = ""
    request_timeout: int = 30
    user_agent: str = "DOU-LeisMPs/0.1"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
