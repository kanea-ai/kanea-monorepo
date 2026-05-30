variable "environment" {
  type        = string
  description = "Target environment for this apply: 'prod' or 'staging'."
  validation {
    condition     = contains(["prod", "staging"], var.environment)
    error_message = "environment must be one of: prod, staging."
  }
}

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

variable "db_availability_type" {
  type        = string
  description = "REGIONAL (HA, prod) or ZONAL (single-zone, staging). Per Cloud SQL pricing this is the dominant cost lever."
  default     = "REGIONAL"
  validation {
    condition     = contains(["REGIONAL", "ZONAL"], var.db_availability_type)
    error_message = "db_availability_type must be REGIONAL or ZONAL."
  }
}

variable "db_disk_size" {
  type    = number
  default = 50
}

variable "db_name" {
  type    = string
  default = "kanea"
}

variable "db_user" {
  type    = string
  default = "kanea_app"
}

variable "cloud_run_max_instances" {
  type        = number
  description = "Per-service max scaling. Cap aggressively in non-prod envs to keep cost predictable."
  default     = 20
}

variable "google_oauth_client_id" {
  type        = string
  description = "Google OAuth client ID. Not sensitive (visible in URLs anyway). Empty disables Google SSO for the env."
  default     = ""
}

variable "github_oauth_client_id" {
  type        = string
  description = "GitHub OAuth client ID. Empty disables GitHub SSO for the env."
  default     = ""
}

variable "staging_allow_ip" {
  type        = string
  description = "CIDR allowlisted for the staging Cloud Armor policy (deny-all otherwise). Ignored in prod. Default is the RFC 5737 documentation range so a fresh apply never accidentally grants real-world access."
  default     = "203.0.113.42/32"
}

variable "admin_iap_member" {
  type        = string
  description = "IAM member granted roles/iap.httpsResourceAccessor on the admin-panel backend. Use a Workspace group (`group:engineering@kanea.ai`) so membership changes don't require Tofu applies. The IAP edge gate runs BEFORE the request reaches Cloud Run, so this is the primary access boundary for the back-office; the in-app Superadmin JWT is the second layer."
  default     = "group:engineering@kanea.ai"
}

variable "admin_iap_support_email" {
  type        = string
  description = "Support email shown on the IAP OAuth consent screen. Must be a Workspace group or a user the apply identity owns."
  default     = "engineering@kanea.ai"
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
