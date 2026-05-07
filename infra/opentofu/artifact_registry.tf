# Artifact Registry repo is shared across envs — image tags (commit SHA)
# distinguish prod / staging revisions, so a single repo is enough. Created
# in prod state only; staging uses it without managing it.

resource "google_artifact_registry_repository" "kanea" {
  count = local.is_prod ? 1 : 0

  location      = var.region
  repository_id = "kanea"
  description   = "Container images for Kanea Cloud Run services."
  format        = "DOCKER"

  cleanup_policies {
    id     = "keep-recent-50"
    action = "KEEP"
    most_recent_versions {
      keep_count = 50
    }
  }

  cleanup_policies {
    id     = "delete-untagged-after-7d"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s"
    }
  }
}

moved {
  from = google_artifact_registry_repository.kanea
  to   = google_artifact_registry_repository.kanea[0]
}

locals {
  artifact_registry_host = "${var.region}-docker.pkg.dev"
  # Hardcoded repo path — staging needs this for image references but doesn't
  # own the repo resource. Prod's resource exists at index [0] when applied;
  # in either env, the path is the same string.
  artifact_registry_path = "${local.artifact_registry_host}/${var.project_id}/kanea"
}
