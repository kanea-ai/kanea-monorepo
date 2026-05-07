# Global External Application Load Balancer (EXTERNAL_MANAGED scheme),
# fronting Cloud Run via serverless NEGs. Hostname-based routing:
#
#   kanea.ai      / www.kanea.ai  -> www       (marketing, default)
#   app.kanea.ai                  -> web-app   (SaaS dashboard)
#   *           / /api/*          -> api       (FastAPI), regardless of host
#
# Subdomain isolation (vs path-based /app/*) keeps Next.js configs clean
# (no basePath/assetPrefix threading) and gives the SaaS app its own
# cookie/localStorage origin.

resource "google_compute_region_network_endpoint_group" "neg" {
  for_each = google_cloud_run_v2_service.svc

  name                  = "neg-${each.key}${local.name_suffix}"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = each.value.name
  }
}

resource "google_compute_backend_service" "svc" {
  for_each = google_cloud_run_v2_service.svc

  name                  = "be-${each.key}${local.name_suffix}"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  security_policy       = google_compute_security_policy.edge.id

  backend {
    group = google_compute_region_network_endpoint_group.neg[each.key].id
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

resource "google_compute_url_map" "main" {
  name = "kanea-url-map${local.name_suffix}"

  # Anything that doesn't match a host_rule below falls through to www.
  # Marketing site is the safe public default.
  default_service = google_compute_backend_service.svc["www"].id

  # Apex + www subdomain → marketing site, with /api/* still hitting the api.
  host_rule {
    hosts        = [var.domain, "www.${var.domain}"]
    path_matcher = "marketing"
  }

  path_matcher {
    name            = "marketing"
    default_service = google_compute_backend_service.svc["www"].id

    path_rule {
      paths   = ["/api", "/api/*"]
      service = google_compute_backend_service.svc["api"].id
    }
  }

  # SaaS subdomain → web-app, with /api/* hitting the api so the api
  # client at `${origin}/api/v1/...` works without cross-origin requests.
  host_rule {
    hosts        = ["app.${var.domain}"]
    path_matcher = "app"
  }

  path_matcher {
    name            = "app"
    default_service = google_compute_backend_service.svc["web-app"].id

    path_rule {
      paths   = ["/api", "/api/*"]
      service = google_compute_backend_service.svc["api"].id
    }
  }
}

# Original cert covers the marketing surface (apex + www). Untouched by
# this PR so prod TLS for kanea.ai / www.kanea.ai is uninterrupted.
resource "google_compute_managed_ssl_certificate" "main" {
  name = "kanea-managed-cert${local.name_suffix}"

  managed {
    domains = [var.domain, "www.${var.domain}"]
  }
}

# Separate cert for the SaaS subdomain. Created independently rather than
# adding `app.${var.domain}` to the existing SAN list — Google managed
# certs are immutable on `domains`, so a SAN change forces destroy+create.
# Two-cert + both-attached avoids that recreate.
resource "google_compute_managed_ssl_certificate" "app" {
  name = "kanea-managed-cert-app${local.name_suffix}"

  managed {
    domains = ["app.${var.domain}"]
  }
}

resource "google_compute_target_https_proxy" "main" {
  name    = "kanea-https-proxy${local.name_suffix}"
  url_map = google_compute_url_map.main.id
  ssl_certificates = [
    google_compute_managed_ssl_certificate.main.id,
    google_compute_managed_ssl_certificate.app.id,
  ]
}

resource "google_compute_global_address" "lb" {
  name = "kanea-lb-ip${local.name_suffix}"
}

resource "google_compute_global_forwarding_rule" "https" {
  name                  = "kanea-https-fr${local.name_suffix}"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  port_range            = "443"
  target                = google_compute_target_https_proxy.main.id
  ip_address            = google_compute_global_address.lb.address
}

# HTTP → HTTPS redirect.
resource "google_compute_url_map" "http_redirect" {
  name = "kanea-http-redirect${local.name_suffix}"

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_target_http_proxy" "redirect" {
  name    = "kanea-http-proxy${local.name_suffix}"
  url_map = google_compute_url_map.http_redirect.id
}

resource "google_compute_global_forwarding_rule" "http" {
  name                  = "kanea-http-fr${local.name_suffix}"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  port_range            = "80"
  target                = google_compute_target_http_proxy.redirect.id
  ip_address            = google_compute_global_address.lb.address
}
