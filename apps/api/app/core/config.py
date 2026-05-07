from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # `.env.development` carries shared dev defaults (committed).
        # `.env` carries personal overrides (gitignored). Later files win,
        # so personal overrides take precedence over shared defaults, and
        # actual environment variables (Cloud Run secrets) win over both.
        env_file=(".env.development", ".env"),
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

    # CORS allow-list. Empty in prod (LB serves api and web-app on the same
    # origin). Populated locally so the Next.js dev servers (3000/3001/3002)
    # can call this api running on :8000.
    cors_origins: list[str] = []


settings = Settings()
