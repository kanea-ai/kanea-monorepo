variable "project_id" {
  type    = string
  default = "kanea-prod-env"
}

variable "region" {
  type    = string
  default = "europe-west1"
}

variable "domain" {
  type        = string
  description = "Public domain served by the load balancer (used for the managed certificate)."
  default     = "kanea.ai"
}

variable "db_tier" {
  type    = string
  default = "db-custom-2-7680"
}

variable "db_name" {
  type    = string
  default = "kanea"
}

variable "db_user" {
  type    = string
  default = "kanea_app"
}

# Bootstrap placeholder. Cloud Run requires an image to create the service so
# the LB can attach a serverless NEG; CD overwrites these with the real images
# pushed to Artifact Registry. Combined with ignore_changes on the image
# attribute (see cloudrun.tf), Tofu won't fight the pipeline on subsequent runs.
variable "images" {
  type = map(string)
  default = {
    api         = "us-docker.pkg.dev/cloudrun/container/hello"
    web-app     = "us-docker.pkg.dev/cloudrun/container/hello"
    admin-panel = "us-docker.pkg.dev/cloudrun/container/hello"
    www         = "us-docker.pkg.dev/cloudrun/container/hello"
  }
}
