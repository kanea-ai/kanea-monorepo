locals {
  services = ["api", "web-app", "admin-panel", "www"]

  # Service names suffixed per env so api-staging and api can coexist.
  # In prod, `name_suffix` is empty so the existing service `api` is
  # preserved (no state churn).
  service_name = { for s in local.services : s => "${s}${local.name_suffix}" }
}

resource "google_service_account" "run" {
  for_each     = toset(local.services)
  account_id   = "run-${each.key}${local.name_suffix}"
  display_name = "Cloud Run SA for ${each.key} (${var.environment})"
}

resource "google_project_iam_member" "run_sql_client" {
  for_each = toset(local.services)
  project  = var.project_id
  role     = "roles/cloudsql.client"
  member   = "serviceAccount:${google_service_account.run[each.key].email}"
}

resource "google_cloud_run_v2_service" "svc" {
  for_each = toset(local.services)

  name     = local.service_name[each.key]
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.run[each.key].email

    scaling {
      min_instance_count = 0
      max_instance_count = var.cloud_run_max_instances
    }

    vpc_access {
      connector = google_vpc_access_connector.main.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = var.images[each.key]

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      # DATABASE_URL is only injected on the api service. The Next.js
      # services don't talk to the DB directly — keeping the secret off
      # their service specs avoids unnecessary IAM grants.
      dynamic "env" {
        for_each = each.key == "api" ? toset(["api"]) : toset([])
        content {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.db_url.secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  # CD deploys new revisions out-of-band by setting the image tag. Tofu owns
  # the service shape (resources, env, scaling, ingress) but defers to the
  # pipeline on which image tag is currently live. `client`/`client_version`
  # are stamped onto the resource by Cloud Run on every `gcloud run services
  # update`; ignoring them prevents Tofu from rolling spurious revisions on
  # the existing image (which can be broken mid-rollout).
  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [google_secret_manager_secret_iam_member.api_db_url_accessor]
}

# Allow public invocation through the load balancer for the three public-facing
# services. admin-panel is intentionally excluded — it stays private and will
# get a scoped invoker grant when access requirements are decided.
locals {
  public_services = ["web-app", "www", "api"]
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  for_each = toset(local.public_services)
  name     = google_cloud_run_v2_service.svc[each.key].name
  location = google_cloud_run_v2_service.svc[each.key].location
  role     = "roles/run.invoker"
  member   = "allUsers"

  # The org-policy override below must exist before this binding can be
  # written. It only exists in prod state (count-gated), so for staging the
  # binding still works because the override is project-scoped — once prod
  # has applied it, both envs benefit.
  depends_on = [google_org_policy_policy.allowed_policy_member_domains]
}
