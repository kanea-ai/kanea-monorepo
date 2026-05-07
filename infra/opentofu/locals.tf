# Cross-env helpers used by every other .tf file.
#
# `name_suffix` is empty for prod so this refactor is a no-op on prod state —
# every resource name keeps its existing form (`kanea-vpc`, `kanea-pg-15`,
# `kanea-edge-armor`, etc.). Staging adds `-staging` so the two envs can
# coexist in the same GCP project without collisions.

locals {
  is_prod     = var.environment == "prod"
  name_suffix = local.is_prod ? "" : "-${var.environment}"

  # Hardcoded email rather than a reference because `google_service_account
  # .github_deployer` is conditionally created (only in prod state). Staging
  # configs need to bind IAM to this SA without going through prod state.
  deployer_sa_email = "github-deployer@${var.project_id}.iam.gserviceaccount.com"

  # VPC connector names are capped at 25 chars. `kanea-vpc-connector` (19) +
  # `-staging` (8) = 27 → over. Use a shorter form for non-prod envs that
  # keeps the prod name intact.
  vpc_connector_name = local.is_prod ? "kanea-vpc-connector" : "kanea-vpc-${var.environment}"

  # Per-env private IP range so debugging across envs isn't ambiguous, even
  # though the VPCs are isolated and could safely overlap.
  app_subnet_cidr           = local.is_prod ? "10.10.0.0/24" : "10.20.0.0/24"
  vpc_connector_subnet_cidr = local.is_prod ? "10.10.8.0/28" : "10.20.8.0/28"
}
