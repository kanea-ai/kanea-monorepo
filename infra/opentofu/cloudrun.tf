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

      # ---------- OAuth env (api-only) ----------
      # Plaintext: provider client IDs (not sensitive), API_BASE_URL +
      # OAUTH_POST_LOGIN_REDIRECT (env-derived URLs), COOKIE_SECURE flag.
      # Secret Manager: the two client secrets, mounted via secret_key_ref.
      dynamic "env" {
        for_each = each.key == "api" ? toset(["api"]) : toset([])
        content {
          name  = "GOOGLE_OAUTH_CLIENT_ID"
          value = var.google_oauth_client_id
        }
      }

      dynamic "env" {
        for_each = each.key == "api" ? toset(["api"]) : toset([])
        content {
          name = "GOOGLE_OAUTH_CLIENT_SECRET"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.google_oauth_client_secret.secret_id
              version = "latest"
            }
          }
        }
      }

      dynamic "env" {
        for_each = each.key == "api" ? toset(["api"]) : toset([])
        content {
          name  = "GITHUB_OAUTH_CLIENT_ID"
          value = var.github_oauth_client_id
        }
      }

      dynamic "env" {
        for_each = each.key == "api" ? toset(["api"]) : toset([])
        content {
          name = "GITHUB_OAUTH_CLIENT_SECRET"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.github_oauth_client_secret.secret_id
              version = "latest"
            }
          }
        }
      }

      dynamic "env" {
        for_each = each.key == "api" ? toset(["api"]) : toset([])
        content {
          name  = "API_BASE_URL"
          value = "https://app.${var.domain}"
        }
      }

      dynamic "env" {
        for_each = each.key == "api" ? toset(["api"]) : toset([])
        content {
          name  = "OAUTH_POST_LOGIN_REDIRECT"
          value = "https://app.${var.domain}/auth/callback"
        }
      }

      dynamic "env" {
        for_each = each.key == "api" ? toset(["api"]) : toset([])
        content {
          name  = "COOKIE_SECURE"
          value = "true"
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

  depends_on = [
    google_secret_manager_secret_iam_member.api_db_url_accessor,
    google_secret_manager_secret_iam_member.api_google_oauth_accessor,
    google_secret_manager_secret_iam_member.api_github_oauth_accessor,
  ]
}

# Allow public invocation through the load balancer for the three public-facing
# services. admin-panel is intentionally excluded — it sits behind IAP at the
# LB edge (see ``iap.tf``) plus the in-app Superadmin gate.
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

# Admin-panel invoker. Scoped to the IAP Service Agent — the only
# identity that should ever invoke this service. The agent is the
# principal IAP uses to call backends on a signed-in user's behalf
# after the LB-edge gate passes; granting it ``roles/run.invoker``
# (and no one else) means a request that somehow bypasses both IAP
# and the ingress check still gets rejected at Cloud Run's IAM.
#
# Defence-in-depth: ingress=internal-LB-only + IAP at the LB +
# IAM-scoped invoker. Each layer is independently sufficient to
# refuse a request; all three have to fail for the back-office to
# leak. Earlier revisions of this file used ``allUsers`` here
# (relying on the first two layers); we tightened to the IAP SA
# after the agent's first request to the backend surfaced "The IAP
# service account is not provisioned" — which forced the agent's
# explicit existence into the runbook anyway.
#
# The IAP Service Agent must exist before this binding can be
# written: ``gcloud beta services identity create --service=
# iap.googleapis.com --project=<id>``. It is a one-shot per
# project (not Tofu-tracked).
resource "google_cloud_run_v2_service_iam_member" "admin_panel_invoker" {
  count = local.is_prod ? 1 : 0

  name     = google_cloud_run_v2_service.svc["admin-panel"].name
  location = google_cloud_run_v2_service.svc["admin-panel"].location
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-iap.iam.gserviceaccount.com"

  depends_on = [
    google_org_policy_policy.allowed_policy_member_domains,
    # IAP must be on the backend service before we open the invoker
    # binding — order matters here because between the binding and
    # IAP enable, the back-office would be reachable unauthenticated
    # if an LB rule already existed.
    google_iap_web_backend_service_iam_member.admin_panel_accessor,
  ]
}
