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

# ---------- Agent API-key pepper (DEPLOY-TIME TODO, blocked on follow-up infra PR) ----------
#
# The HMAC pepper backing `agent_api_keys.secret_hash`. Added in the
# API PR that introduced per-agent keys. The api refuses to boot in
# any non-development environment with the committed placeholder
# (see apps/api/app/core/config.py:_check_pepper_set_in_prod), so a
# Tofu apply that lands the api image without ALSO landing this
# wiring will surface as a hard Cloud Run startup failure with
#
#   ValueError: agent_api_key_pepper is set to the committed
#   placeholder in a non-development environment ('production').
#
# That's the intended behavior — better a loud boot failure than a
# silent default secret. It does mean the four steps below must land
# together in a single deploy.
#
# Uncomment + apply in the follow-up infra PR:
#
#   1. The secret container + initial placeholder version.
#      Replace the placeholder via:
#        head -c 48 /dev/urandom | base64 | gcloud secrets versions add \
#          agent-api-key-pepper --data-file=- --project=kanea-prod-env
#      Treat each env's pepper as independent — never share live + staging.
#
#   2. The secretAccessor IAM grant on the run-api SA (same shape as
#      `api_db_url_accessor` / `api_google_oauth_accessor` above).
#
#   3. Mount as `AGENT_API_KEY_PEPPER` on the api Cloud Run service —
#      add a `secret_key_ref` env binding in cloudrun.tf alongside the
#      existing DB URL one. `version = "latest"` so a future rotation
#      via `gcloud secrets versions add` flows on the next revision
#      rollout.
#
#   4. Set `AGENT_API_KEY_ENV_TAG=live` as a plain env var on the prod
#      api service (and leave it unset / `dev` everywhere else). The
#      exchange endpoint refuses keys whose env-tag doesn't match, so a
#      dev key leaked into prod cannot mint a JWT and vice versa.
#
# Operational consequence (also in the api's config.py docstring):
# rotating or losing this pepper invalidates every existing agent API
# key — plaintext is never persisted, so rotation = mint fresh keys
# under the new pepper, then revoke the old ones.
#
# resource "google_secret_manager_secret" "agent_api_key_pepper" {
#   secret_id = "agent-api-key-pepper${local.name_suffix}"
#   replication {
#     auto {}
#   }
# }
#
# resource "google_secret_manager_secret_version" "agent_api_key_pepper" {
#   secret      = google_secret_manager_secret.agent_api_key_pepper.id
#   secret_data = "PLACEHOLDER_SET_VIA_GCLOUD" # pragma: allowlist secret
#   lifecycle {
#     ignore_changes = [secret_data]
#   }
# }
#
# resource "google_secret_manager_secret_iam_member" "api_agent_api_key_pepper_accessor" {
#   secret_id = google_secret_manager_secret.agent_api_key_pepper.id
#   role      = "roles/secretmanager.secretAccessor"
#   member    = "serviceAccount:${google_service_account.run["api"].email}"
# }
