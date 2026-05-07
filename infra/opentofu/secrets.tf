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
    "postgresql+asyncpg://%s:%s@%s:5432/%s",  # pragma: allowlist secret
    google_sql_user.app.name,
    urlencode(random_password.db.result),
    google_sql_database_instance.main.private_ip_address,
    google_sql_database.app.name,
  )
}

resource "google_secret_manager_secret" "db_url" {
  secret_id = "kanea-db-url"

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
