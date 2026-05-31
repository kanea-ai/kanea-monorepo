from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel value committed to the repo so local dev / unit tests can
# boot without a real pepper. The validator below refuses to start
# when this value is still present AND the environment is anything
# other than "development". Treat this constant as a tripwire — never
# rename it without also fixing the env files that ship it.
_DEV_PEPPER_PLACEHOLDER = "change-me-in-production-agent-pepper"  # pragma: allowlist secret


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

    # Server-side pepper for the agent API-key lookup hash. The body of
    # a `kna_<env>_<body>` key is HMAC-SHA-256'd with this pepper to
    # derive the `agent_api_keys.secret_hash` column. The HMAC (vs bare
    # SHA-256) means a DB-only compromise cannot verify guessed or
    # leaked key bodies without also stealing this app secret.
    #
    # Operational consequence (LOAD-BEARING — surface this in ops docs):
    #   If this pepper is ever rotated or lost, every existing agent
    #   API key stops verifying — there is NO re-hash path because the
    #   plaintext is never persisted. Rotation = mint new keys under
    #   the new pepper, hand them to operators, revoke the old keys.
    #
    # In prod this MUST come from Secret Manager. The committed default
    # is a sentinel that the validator below refuses in any non-dev
    # environment — see ``_check_pepper_set_in_prod``.
    agent_api_key_pepper: str = _DEV_PEPPER_PLACEHOLDER

    # `live` (prod) / `dev` (everything else). Embedded in agent API
    # keys as `kna_<env>_<body>`; the exchange endpoint refuses to
    # accept a key whose env-tag doesn't match this setting, so a
    # dev-env key leaked into prod (or vice-versa) cannot mint a JWT.
    agent_api_key_env_tag: str = "dev"

    @model_validator(mode="after")
    def _check_pepper_set_in_prod(self) -> Settings:
        """Refuse to boot in any non-development environment when the
        agent API-key pepper still carries the committed sentinel.
        Equivalent to a startup tripwire — better to crash on import
        than to silently accept the placeholder secret in prod."""
        if (
            self.environment != "development"
            and self.agent_api_key_pepper == _DEV_PEPPER_PLACEHOLDER
        ):
            raise ValueError(
                "agent_api_key_pepper is set to the committed placeholder in a "
                f"non-development environment ({self.environment!r}). Provide a "
                "real pepper via Secret Manager / env var before booting."
            )
        return self

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
