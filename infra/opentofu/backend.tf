terraform {
  backend "gcs" {
    bucket = "kanea-tofu-state-prod"
    prefix = "terraform/state"
  }
}
