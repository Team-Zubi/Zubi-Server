from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Zubi Server"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    # 쉼표로 구분된 허용 Origin 목록 (예: "http://localhost:3000,https://zubi.app")
    cors_origins: list[str] = ["*"]

    # PostgreSQL + PostGIS (API·수집기 공용)
    database_url: str = "postgresql+psycopg://zubi:zubi@localhost:5432/zubi"

    # 공공 API 키 — .env에만 둔다 (커밋 금지). 비어 있으면 해당 출처는 수집하지 않는다.
    seoul_api_key: str = ""
    gg_api_key: str = ""

    # 수집기
    collector_interval_seconds: int = 300
    collector_http_timeout_seconds: float = 20.0
    collector_http_retries: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
