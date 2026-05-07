# Workload Identity Federation: GitHub Actions authenticates to GCP via OIDC,
# no service-account JSON keys checked in or stored in repo secrets.
#
# Pool / provider / deployer SA / project-level IAM grants are project-scoped
# singletons — they exist once across all envs. Keeping them in the prod
# state (count-gated below) means staging applies don't try to recreate them.
# Staging still uses the same deployer SA via `local.deployer_sa_email`,
# which is bound on staging runtime SAs through the per-env act_as grant
# at the bottom of this file.

variable "github_repository" {
  type        = string
  description = "GitHub <owner>/<repo> allowed to assume the deploy SA."
  default     = "kanea-ai/kanea-monorepo"
}

# `moved` blocks tell Tofu to migrate the existing prod state from the
# unindexed address to the count[0] address without destroy/recreate. They
# are a no-op once state is migrated and safe to keep.

resource "google_iam_workload_identity_pool" "github" {
  count                     = local.is_prod ? 1 : 0
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions Pool"
  description               = "WIF pool for GitHub Actions OIDC."
}

moved {
  from = google_iam_workload_identity_pool.github
  to   = google_iam_workload_identity_pool.github[0]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count                              = local.is_prod ? 1 : 0
  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
    "attribute.ref"              = "assertion.ref"
  }

  attribute_condition = "assertion.repository == \"${var.github_repository}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

moved {
  from = google_iam_workload_identity_pool_provider.github
  to   = google_iam_workload_identity_pool_provider.github[0]
}

resource "google_service_account" "github_deployer" {
  count        = local.is_prod ? 1 : 0
  account_id   = "github-deployer"
  display_name = "GitHub Actions Cloud Run deployer"
}

moved {
  from = google_service_account.github_deployer
  to   = google_service_account.github_deployer[0]
}

# Push images to Artifact Registry. AR repo is prod-only too (see
# artifact_registry.tf) — staging shares the same repo, image tags
# distinguish revisions across envs.
resource "google_artifact_registry_repository_iam_member" "deployer_writer" {
  count      = local.is_prod ? 1 : 0
  location   = google_artifact_registry_repository.kanea[0].location
  repository = google_artifact_registry_repository.kanea[0].name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.github_deployer[0].email}"
}

moved {
  from = google_artifact_registry_repository_iam_member.deployer_writer
  to   = google_artifact_registry_repository_iam_member.deployer_writer[0]
}

# Update Cloud Run services (deploy new revisions) — project-scoped, applies
# to both prod and staging Cloud Run services.
resource "google_project_iam_member" "deployer_run_admin" {
  count   = local.is_prod ? 1 : 0
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_deployer[0].email}"
}

moved {
  from = google_project_iam_member.deployer_run_admin
  to   = google_project_iam_member.deployer_run_admin[0]
}

# Allow the deployer to actAs the per-env runtime SAs. Lives in EACH env's
# state because it binds to env-specific SAs (run-api / run-api-staging).
# Member is the shared deployer SA (referenced by hardcoded email so this
# binding works in staging without reading prod state).
resource "google_service_account_iam_member" "deployer_act_as_runtime" {
  for_each = google_service_account.run

  service_account_id = each.value.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${local.deployer_sa_email}"
}

# The actual federation: only GitHub Actions runs from the configured repo
# can impersonate the deploy SA. Both `dev` (staging) and `main` (prod)
# branches authenticate through the same SA; per-branch isolation would
# need separate SAs + branch-scoped principalSets, deferred for later.
resource "google_service_account_iam_member" "deployer_wif_binding" {
  count              = local.is_prod ? 1 : 0
  service_account_id = google_service_account.github_deployer[0].name
  role               = "roles/iam.workloadIdentityUser"
  member = format(
    "principalSet://iam.googleapis.com/%s/attribute.repository/%s",
    google_iam_workload_identity_pool.github[0].name,
    var.github_repository,
  )
}

moved {
  from = google_service_account_iam_member.deployer_wif_binding
  to   = google_service_account_iam_member.deployer_wif_binding[0]
}
