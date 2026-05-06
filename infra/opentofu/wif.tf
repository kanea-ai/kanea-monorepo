# Workload Identity Federation: GitHub Actions authenticates to GCP via OIDC,
# no service-account JSON keys checked in or stored in repo secrets.

variable "github_repository" {
  type        = string
  description = "GitHub <owner>/<repo> allowed to assume the deploy SA."
  default     = "kanea-ai/kanea-monorepo"
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions Pool"
  description               = "WIF pool for GitHub Actions OIDC."
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
    "attribute.ref"              = "assertion.ref"
  }

  # Belt-and-braces: only tokens issued for the configured repo can pass.
  # The principalSet binding below independently restricts to the same repo.
  attribute_condition = "assertion.repository == \"${var.github_repository}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "github_deployer" {
  account_id   = "github-deployer"
  display_name = "GitHub Actions Cloud Run deployer"
}

# Push images to Artifact Registry.
resource "google_artifact_registry_repository_iam_member" "deployer_writer" {
  location   = google_artifact_registry_repository.kanea.location
  repository = google_artifact_registry_repository.kanea.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.github_deployer.email}"
}

# Update Cloud Run services (deploy new revisions).
resource "google_project_iam_member" "deployer_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

# Allow the deployer to actAs the per-service runtime SAs created in cloudrun.tf.
# Bound per-SA rather than project-wide to keep the blast radius tight.
resource "google_service_account_iam_member" "deployer_act_as_runtime" {
  for_each = google_service_account.run

  service_account_id = each.value.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_deployer.email}"
}

# The actual federation: only GitHub Actions runs from the configured repo
# can impersonate the deploy SA.
resource "google_service_account_iam_member" "deployer_wif_binding" {
  service_account_id = google_service_account.github_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member = format(
    "principalSet://iam.googleapis.com/%s/attribute.repository/%s",
    google_iam_workload_identity_pool.github.name,
    var.github_repository,
  )
}
