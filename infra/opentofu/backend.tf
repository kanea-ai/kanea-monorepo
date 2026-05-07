terraform {
  backend "gcs" {
    bucket = "kanea-tofu-state-prod"
    # `prefix` is supplied per-env at init time:
    #   prod    : -backend-config="prefix=terraform/state"
    #   staging : -backend-config="prefix=terraform/state/staging"
    # See .github/workflows/deploy.yml. Prod's prefix matches the
    # historical path so this refactor doesn't move existing state.
  }
}
