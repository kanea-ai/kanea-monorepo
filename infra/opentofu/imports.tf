# One-shot imports of Cloud Run services that were created out-of-band by the
# deploy workflow before Tofu could finish its own apply. Required because the
# original `tofu apply` failed on missing Service Networking / Serverless VPC
# Access APIs, so `google_cloud_run_v2_service.svc[*]` never made it into
# state — but the GitHub Actions deploy then created them anyway via gcloud.
#
# These blocks are idempotent: once the resources are in state, future plans
# treat them as no-ops. Safe to delete after the next clean plan, but keeping
# them is also fine.

import {
  to = google_cloud_run_v2_service.svc["api"]
  id = "projects/${var.project_id}/locations/${var.region}/services/api"
}

import {
  to = google_cloud_run_v2_service.svc["web-app"]
  id = "projects/${var.project_id}/locations/${var.region}/services/web-app"
}

import {
  to = google_cloud_run_v2_service.svc["www"]
  id = "projects/${var.project_id}/locations/${var.region}/services/www"
}

import {
  to = google_cloud_run_v2_service.svc["admin-panel"]
  id = "projects/${var.project_id}/locations/${var.region}/services/admin-panel"
}
