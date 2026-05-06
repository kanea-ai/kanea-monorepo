resource "google_artifact_registry_repository" "kanea" {
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

locals {
  artifact_registry_host = "${var.region}-docker.pkg.dev"
  artifact_registry_path = "${local.artifact_registry_host}/${var.project_id}/${google_artifact_registry_repository.kanea.repository_id}"
}
