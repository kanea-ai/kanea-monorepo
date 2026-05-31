from __future__ import annotations

from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel values for required-in-prod secret placeholders. Both kept
# as named constants so tests and the unified validator below can
# reference them without re-typing the literal — and so detect-secrets
# tooling can be allowlisted on this single line per secret rather than
# every call site.
#
# Provenance:
#
# - ``agent_api_key_pepper`` protection was introduced in PRs #39-#41
#   as a standalone ``_check_pepper_set_in_prod`` validator + Tofu
#   wiring. The standalone validator was folded into the unified
#   ``_check_required_secrets_in_prod`` below in the issue-#42 work;
#   protection is unchanged (same trigger condition, same fail-loud at
#   import).
#
# - ``jwt_secret`` protection lands as the second occupant via issue
#   #42. The wiring (Phase A + Phase B Tofu) follows the same shape
#   as PRs #40 / #41.
_DEV_JWT_SECRET_PLACEHOLDER = "change-me-in-production"  # pragma: allowlist secret
_DEV_PEPPER_PLACEHOLDER = "change-me-in-production-agent-pepper"  # pragma: allowlist secret

# Registry of (field, placeholder) pairs the unified validator
# enforces in any non-development environment. Adding a new
# required-in-prod secret = one line here, the field declaration
# below, and the matching Tofu wiring (Phase A container + Phase B
# secret_key_ref binding).
_REQUIRED_IN_PROD_PLACEHOLDERS: tuple[tuple[str, str], ...] = (
    ("jwt_secret", _DEV_JWT_SECRET_PLACEHOLDER),
    ("agent_api_key_pepper", _DEV_PEPPER_PLACEHOLDER),
)

# Explicit environment whitelist. The ``Settings.environment`` field
# below is typed as this Literal WITH NO DEFAULT, so pydantic refuses
# both "unset" (no env var supplied → field-required error) and
# "invalid" (typo → enum-value error) BEFORE the model_validator
# below runs. That ordering is non-negotiable: it ensures a broken
# ENVIRONMENT is always reported as its own pydantic field error,
# never as a misleading cascade of "secret X is the placeholder"
# downstream errors that are really just symptoms of environment
# never being set.
Environment = Literal["development", "staging", "production"]


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

    # No default. Pydantic raises "field required" when ENVIRONMENT
    # isn't supplied. Local dev gets it from .env.development
    # (committed, sets ENVIRONMENT=development); CI's pytest job runs
    # from apps/api/ so it picks up the same file; prod / staging
    # Cloud Run set it via cloudrun.tf. A future deploy that forgets
    # the binding crashes on import rather than silently no-op'ing
    # every prod-only validator below.
    environment: Environment

    database_url: str = (
        "postgresql+asyncpg://kanea:kanea@localhost:5432/kanea"  # pragma: allowlist secret
    )
    database_echo: bool = False

    jwt_secret: str = _DEV_JWT_SECRET_PLACEHOLDER
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
    # is a sentinel that ``_check_required_secrets_in_prod`` refuses in
    # any non-development environment.
    agent_api_key_pepper: str = _DEV_PEPPER_PLACEHOLDER

    # `live` (prod) / `dev` (everything else). Embedded in agent API
    # keys as `kna_<env>_<body>`; the exchange endpoint refuses to
    # accept a key whose env-tag doesn't match this setting, so a
    # dev-env key leaked into prod (or vice-versa) cannot mint a JWT.
    agent_api_key_env_tag: str = "dev"

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

    @model_validator(mode="after")
    def _check_required_secrets_in_prod(self) -> Settings:
        """Unified tripwire for required-in-prod secrets.

        By the time this validator runs, pydantic has already validated
        ``environment`` against the ``Environment`` Literal — an unset
        or invalid ENVIRONMENT raises a field error BEFORE this method
        runs. So "ENVIRONMENT is broken" is always its own pydantic
        field error, never cascading into a misleading list of
        "secret X is the placeholder" downstream errors that are really
        just symptoms of environment-never-set. That ordering is
        non-negotiable and is the reason this validator does not
        re-check ``environment`` itself.

        When ``environment != "development"``, every registered
        required-in-prod secret must carry a non-placeholder value.
        Multiple offenders are aggregated into a single error so a
        fresh deploy that forgot all of them surfaces a readable
        list, not three deploys-worth of fix-one-at-a-time.

        Security invariant: the error message names FIELDS, never
        VALUES. No placeholder string (and by extension no real
        value, since both go through the same code path) is
        included in the error. Pinned by
        ``test_both_placeholders_aggregated_in_one_error``.

        Pepper provenance: PRs #39-#41 introduced the standalone
        ``_check_pepper_set_in_prod`` validator and the Tofu wiring
        that feeds it. That standalone validator was folded into this
        unified rule in the issue-#42 work — protection is unchanged
        (same trigger: environment != "development" AND value ==
        placeholder, same fail-loud at import).
        """
        if self.environment == "development":
            return self

        offenders = [
            name
            for name, placeholder in _REQUIRED_IN_PROD_PLACEHOLDERS
            if getattr(self, name) == placeholder
        ]
        if offenders:
            names = ", ".join(offenders)
            verb = "is" if len(offenders) == 1 else "are"
            raise ValueError(
                f"{names} {verb} set to the committed placeholder in "
                f"environment={self.environment!r}. Provide real "
                "value(s) via Secret Manager / env var before booting."
            )
        return self


settings = Settings()
