from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "kanea-api"
    version: str = "0.0.0"
    environment: str = "development"

    database_url: str = (
        "postgresql+asyncpg://kanea:kanea@localhost:5432/kanea"  # pragma: allowlist secret
    )
    database_echo: bool = False

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_human_ttl_seconds: int = 3600
    jwt_agent_ttl_seconds: int = 900
    jwt_issuer: str = "kanea-api"


settings = Settings()
