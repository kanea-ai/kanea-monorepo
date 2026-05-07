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

    # OAuth (Social SSO). Client secrets are pulled from Secret Manager in
    # prod; locally they live in apps/api/.env (gitignored). When unset, the
    # corresponding provider is treated as disabled — /oauth/{provider}/login
    # returns 503 instead of redirecting to a misconfigured authorize URL.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    github_oauth_client_id: str = ""
    github_oauth_client_secret: str = ""

    # Where the api redirects the browser after a successful OAuth callback.
    # The frontend's /auth/callback route reads `?token=…` and stores it.
    # Defaults to localhost for dev; in prod, this is https://app.kanea.ai
    # via env var on the api Cloud Run service.
    oauth_post_login_redirect: str = "http://localhost:3000/auth/callback"

    # Public base URL the api is reachable at for OAuth providers' redirects.
    # Used to construct the `redirect_uri` parameter handed to Google/GitHub —
    # must match what's whitelisted in the provider console exactly.
    api_base_url: str = "http://localhost:8000"

    # Set Secure on the oauth_state cookie. False in local dev (HTTP),
    # True in prod where the LB terminates TLS.
    cookie_secure: bool = False


settings = Settings()
