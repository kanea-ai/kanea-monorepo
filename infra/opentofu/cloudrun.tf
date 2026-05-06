locals {
  services = ["api", "web-app", "admin-panel", "www"]
}

resource "google_service_account" "run" {
  for_each     = toset(local.services)
  account_id   = "run-${each.key}"
  display_name = "Cloud Run SA for ${each.key}"
}

resource "google_project_iam_member" "run_sql_client" {
  for_each = toset(local.services)
  project  = var.project_id
  role     = "roles/cloudsql.client"
  member   = "serviceAccount:${google_service_account.run[each.key].email}"
}

resource "google_cloud_run_v2_service" "svc" {
  for_each = toset(local.services)

  name     = each.key
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    service_account = google_service_account.run[each.key].email

    scaling {
      min_instance_count = 0
      max_instance_count = 20
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

      env {
        name  = "DATABASE_HOST"
        value = google_sql_database_instance.main.private_ip_address
      }
      env {
        name  = "DATABASE_NAME"
        value = google_sql_database.app.name
      }
      env {
        name  = "DATABASE_USER"
        value = google_sql_user.app.name
      }
      env {
        name  = "DATABASE_PASSWORD"
        value = random_password.db.result
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  # CD deploys new revisions out-of-band by setting the image tag. Tofu owns
  # the service shape (resources, env, scaling, ingress) but defers to the
  # pipeline on which image tag is currently live.
  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
    ]
  }
}

# Allow public invocation through the load balancer for the three public-facing
# services. admin-panel is intentionally excluded — it stays private and will
# get a scoped invoker grant (e.g., to an IAP-fronted service account or an
# authenticated identity) when access requirements are decided.
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
  # written; without it, the API rejects allUsers as a member.
  depends_on = [google_org_policy_policy.allowed_policy_member_domains]
}
