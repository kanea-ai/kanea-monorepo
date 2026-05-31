# Database connection URL for the api service.
#
# We compose the SQLAlchemy/asyncpg URL from the Cloud SQL instance's
# private IP, the app DB user, and the random password — and stash the
# whole string in Secret Manager. Cloud Run reads it via env var with
# `secret_key_ref`, so the password never appears in the service spec
# or in `gcloud run services describe` output.
#
# urlencode() on the password is load-bearing: random_password is
# generated with special=true so colons / @ / # would otherwise
# corrupt the URL.

locals {
  db_url = format(
    "postgresql+asyncpg://%s:%s@%s:5432/%s", # pragma: allowlist secret
    google_sql_user.app.name,
    urlencode(random_password.db.result),
    google_sql_database_instance.main.private_ip_address,
    google_sql_database.app.name,
  )
}

resource "google_secret_manager_secret" "db_url" {
  secret_id = "kanea-db-url${local.name_suffix}"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_url" {
  secret      = google_secret_manager_secret.db_url.id
  secret_data = local.db_url
}

# Only the api runtime SA needs to read this. Web-app / www / admin-panel
# never talk to the DB directly — they go through the api over HTTPS.
resource "google_secret_manager_secret_iam_member" "api_db_url_accessor" {
  secret_id = google_secret_manager_secret.db_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.run["api"].email}"
}

# ---------- OAuth client secrets ----------
#
# Tofu manages the secret container + a placeholder version so the api
# Cloud Run service has *something* to read on first deploy and doesn't
# fail to start. After this lands, replace the placeholder with the real
# value via:
#
#   echo -n "<real secret>" | gcloud secrets versions add \
#     google-oauth-client-secret --data-file=- --project=kanea-prod-env
#
# Cloud Run uses `version = "latest"`, so the next revision rollout picks
# up the new value automatically. `lifecycle.ignore_changes` on
# secret_data means subsequent Tofu applies don't fight that update.

resource "google_secret_manager_secret" "google_oauth_client_secret" {
  secret_id = "google-oauth-client-secret${local.name_suffix}"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "google_oauth_client_secret" {
  secret      = google_secret_manager_secret.google_oauth_client_secret.id
  secret_data = "PLACEHOLDER_SET_VIA_GCLOUD" # pragma: allowlist secret

  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret_iam_member" "api_google_oauth_accessor" {
  secret_id = google_secret_manager_secret.google_oauth_client_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.run["api"].email}"
}

resource "google_secret_manager_secret" "github_oauth_client_secret" {
  secret_id = "github-oauth-client-secret${local.name_suffix}"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "github_oauth_client_secret" {
  secret      = google_secret_manager_secret.github_oauth_client_secret.id
  secret_data = "PLACEHOLDER_SET_VIA_GCLOUD" # pragma: allowlist secret

  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret_iam_member" "api_github_oauth_accessor" {
  secret_id = google_secret_manager_secret.github_oauth_client_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.run["api"].email}"
}

# ---------- Agent API-key pepper (Phase A — dormant) ----------
#
# Phase A of the two-PR safe ordering. This file change lands the
# secret CONTAINER + the secretAccessor IAM grant on `run-api`, and
# NOTHING references the secret yet — the api Cloud Run service's
# env spec is untouched in this PR. So applying this PR changes
# nothing about how the running api behaves; the prod-only validator
# in app/core/config.py stays dormant and no revision can boot-fail.
#
# After this PR is applied, the operator runs out-of-band:
#
#   PEPPER=$(head -c 64 /dev/urandom | base64)
#   printf '%s' "$PEPPER" | gcloud secrets versions add \
#     agent-api-key-pepper${local.name_suffix} \
#     --data-file=- --project=<project>
#   unset PEPPER
#
# Phase B (a separate PR) then adds the AGENT_API_KEY_PEPPER
# secret_key_ref binding + ENVIRONMENT=production + AGENT_API_KEY_ENV_TAG=live
# on the api Cloud Run service. By then the real pepper already exists,
# so the first new revision Phase B rolls boots healthy — no deliberate
# failure window.
#
# Operational consequence (also documented in app/core/config.py):
# rotating or losing this pepper invalidates every existing agent API
# key — plaintext is never persisted, so rotation = mint fresh keys
# under the new pepper, then revoke the old ones.
#
# Future rotation: `gcloud secrets versions add` against the existing
# container; Cloud Run reads via `version = "latest"` so the next
# revision rollout picks it up automatically.

resource "google_secret_manager_secret" "agent_api_key_pepper" {
  secret_id = "agent-api-key-pepper${local.name_suffix}"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "agent_api_key_pepper" {
  secret      = google_secret_manager_secret.agent_api_key_pepper.id
  secret_data = "PLACEHOLDER_SET_VIA_GCLOUD" # pragma: allowlist secret

  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret_iam_member" "api_agent_api_key_pepper_accessor" {
  secret_id = google_secret_manager_secret.agent_api_key_pepper.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.run["api"].email}"
}

# ---------- JWT signing secret (Phase A — dormant) ----------
#
# HMAC key for jwt.encode / jwt.decode in apps/api. The same secret
# signs and verifies every JWT the platform issues — human workspace
# tokens, agent JWTs (scope='agent'), selection tokens, and OAuth
# onboarding tickets — via the single signing path on
# ``apps/api/app/infrastructure/security/tokens.py`` and the single
# verification path on ``apps/api/app/api/deps.py:_decode_principal``.
# Rotating the value invalidates every token of every type atomically;
# see issue #42 for the blast-radius analysis that motivated this work.
#
# Phase A of the two-PR safe ordering — same shape as the
# agent_api_key_pepper rollout in PRs #40 / #41. This PR lands the
# secret CONTAINER + secretAccessor IAM grant on `run-api`, and
# NOTHING references the secret yet (no env binding in cloudrun.tf,
# no Settings field expects it). Applying this PR changes nothing
# about how the running api behaves; the existing standalone pepper
# validator stays in force, the api keeps booting on the field-default
# placeholder for `jwt_secret`, and prod continues to serve as it
# does today. The latent issue #42 remains latent until Phase B.
#
# After this PR is applied, the operator runs out-of-band (one per
# environment that gets cut over):
#
#   PROD:
#     JWT_SECRET=$(head -c 64 /dev/urandom | base64)
#     printf '%s' "$JWT_SECRET" | gcloud secrets versions add \
#       jwt-secret --data-file=- --project=kanea-prod-env
#     unset JWT_SECRET
#
#   STAGING (only if cutting staging over):
#     JWT_SECRET=$(head -c 64 /dev/urandom | base64)
#     printf '%s' "$JWT_SECRET" | gcloud secrets versions add \
#       jwt-secret-staging --data-file=- --project=<staging-project-id>
#     unset JWT_SECRET
#
# Phase B (a separate draft PR, ``infra/jwt-secret-arm-validator``)
# then adds the JWT_SECRET secret_key_ref binding on the api Cloud
# Run service AND folds the standalone pepper validator into a unified
# `_check_required_secrets_in_prod` that also enforces jwt_secret. By
# the time Phase B's image rolls, the real secret already exists, so
# the new revision boots reading it on first try — no deliberate-
# failure window.
#
# OPERATIONAL CONSEQUENCE — store the generated value in durable
# secret storage (e.g. a password manager). The value is never
# persisted by the api, never logged, and never recoverable from
# Secret Manager once a newer version is added. Losing it = forced
# rotation = every active session logged out, every agent forced to
# re-exchange its API key. Rotating it deliberately has the same
# effect; see README ops section for the procedure.

resource "google_secret_manager_secret" "jwt_secret" {
  secret_id = "jwt-secret${local.name_suffix}"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "jwt_secret" {
  secret      = google_secret_manager_secret.jwt_secret.id
  secret_data = "PLACEHOLDER_SET_VIA_GCLOUD" # pragma: allowlist secret

  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret_iam_member" "api_jwt_secret_accessor" {
  secret_id = google_secret_manager_secret.jwt_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.run["api"].email}"
}
