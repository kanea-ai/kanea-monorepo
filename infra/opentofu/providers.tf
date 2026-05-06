terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.40"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.40"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region

  # Some APIs (notably orgpolicy.googleapis.com) require a billing/quota
  # project distinct from the resource's project when authenticating with
  # user ADC. Without this, calls fail with SERVICE_DISABLED on the ADC
  # default project even though the API is enabled on kanea-prod-env.
  user_project_override = true
  billing_project       = var.project_id
}

provider "google-beta" {
  project = var.project_id
  region  = var.region

  user_project_override = true
  billing_project       = var.project_id
}
