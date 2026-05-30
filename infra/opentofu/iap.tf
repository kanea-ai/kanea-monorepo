# Identity-Aware Proxy gating for the back-office.
#
# IAP sits at the load-balancer edge: a request that doesn't carry a
# valid IAP-issued cookie / token is bounced to a Google sign-in
# BEFORE it ever reaches Cloud Run. Combined with the existing
# `ingress = INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER` on the admin-
# panel service, this means the only path to the back-office is:
#
#   1. Visitor signs in to Google (any account — our OAuth brand is
#      "External" because the same brand backs the customer-facing
#      SSO at app.kanea.ai; GCP only allows ONE brand per project).
#   2. IAP checks the IAM policy on the IAP-protected backend
#      (`roles/iap.httpsResourceAccessor` on
#      ``google_iap_web_backend_service_iam_member.admin_panel_accessor``).
#      Anyone not in ``var.admin_iap_member`` gets a 403 here, even
#      though the consent screen accepted them.
#   3. LB forwards the request to the admin-panel Cloud Run service,
#      which is reachable only via the LB.
#   4. The Next.js app delegates to the API's SuperadminDep, which
#      cross-checks the platform-level `users.is_superadmin` flag
#      (set out-of-band via `scripts/make_superadmin.py`).
#
# Three layers of defence. Each step is independent: IAP membership
# can be revoked from Workspace without touching code; the in-app
# superadmin flag can be flipped from the CLI without touching IAP.
#
# Only emitted in prod. Staging back-office access is via
# Cloud-Armor + IP-allowlist (existing deny-all-but-developer-IP
# policy on the LB edge), no IAP setup needed there.

# ---------------------------------------------------------------------------
# Why we DON'T manage the OAuth client (or brand) in Tofu
# ---------------------------------------------------------------------------
#
# GCP allows exactly one OAuth brand per project, and ours is
# "External" (app.kanea.ai depends on it for public SSO). GCP refuses
# to create ``google_iap_client`` against an External brand
# (``Error 400: Brand's Application type must be set to Internal.``),
# so the IAP OAuth client was created manually in the Console as a
# standard "Web application" OAuth client and its credentials are
# stashed in Secret Manager. Tofu only READS them here — never writes.
#
# Rotation runbook:
#   1. Console → APIs & Services → Credentials → reset secret on the
#      "Kanea IAP Admin Panel" OAuth client.
#   2. ``echo -n "<new secret>" | gcloud secrets versions add \
#        iap-admin-panel-client-secret --data-file=- \
#        --project=kanea-prod-env``
#   3. ``tofu apply`` (the data source resolves to the latest version,
#      so the new value gets baked into the backend service on the
#      next apply).

data "google_secret_manager_secret_version" "iap_admin_client_id" {
  count   = local.is_prod ? 1 : 0
  project = var.project_id
  secret  = "iap-admin-panel-client-id" # pragma: allowlist secret
}

data "google_secret_manager_secret_version" "iap_admin_client_secret" {
  count   = local.is_prod ? 1 : 0
  project = var.project_id
  secret  = "iap-admin-panel-client-secret" # pragma: allowlist secret
}

# Membership grant — who's actually allowed through the gate.
# Group-scoped so adding / removing access doesn't need a Tofu apply.
# This is the ACTUAL access control: External-brand IAP lets anyone
# reach the consent screen, but the request only progresses past IAP
# if the authenticated principal matches this binding.
resource "google_iap_web_backend_service_iam_member" "admin_panel_accessor" {
  count = local.is_prod ? 1 : 0

  project             = var.project_id
  web_backend_service = google_compute_backend_service.svc["admin-panel"].name
  role                = "roles/iap.httpsResourceAccessor"
  member              = var.admin_iap_member
}
