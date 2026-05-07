# One-shot imports of the four prod Cloud Run services that were created
# out-of-band by the deploy workflow before Tofu could finish its own
# initial apply. Once the resources are in state, future plans treat
# these blocks as no-ops.
#
# Staging applies skip these — the staging Cloud Run services don't exist
# yet, so import would fail. Tofu's `import` block doesn't accept `count`
# directly, so we gate by env via separate blocks (one per service).

import {
  for_each = local.is_prod ? toset(["api"]) : toset([])
  to       = google_cloud_run_v2_service.svc[each.key]
  id       = "projects/${var.project_id}/locations/${var.region}/services/api"
}

import {
  for_each = local.is_prod ? toset(["web-app"]) : toset([])
  to       = google_cloud_run_v2_service.svc[each.key]
  id       = "projects/${var.project_id}/locations/${var.region}/services/web-app"
}

import {
  for_each = local.is_prod ? toset(["www"]) : toset([])
  to       = google_cloud_run_v2_service.svc[each.key]
  id       = "projects/${var.project_id}/locations/${var.region}/services/www"
}

import {
  for_each = local.is_prod ? toset(["admin-panel"]) : toset([])
  to       = google_cloud_run_v2_service.svc[each.key]
  id       = "projects/${var.project_id}/locations/${var.region}/services/admin-panel"
}
