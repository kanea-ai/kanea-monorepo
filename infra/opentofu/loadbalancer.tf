# Global External Application Load Balancer (EXTERNAL_MANAGED scheme),
# fronting Cloud Run via serverless NEGs. URL map sends /api/* to the
# Python Cloud Run; everything else goes to the web-app Cloud Run.

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
  name            = "kanea-url-map${local.name_suffix}"
  default_service = google_compute_backend_service.svc["web-app"].id

  host_rule {
    hosts        = [var.domain, "www.${var.domain}"]
    path_matcher = "main"
  }

  path_matcher {
    name            = "main"
    default_service = google_compute_backend_service.svc["web-app"].id

    path_rule {
      paths   = ["/api", "/api/*"]
      service = google_compute_backend_service.svc["api"].id
    }
  }
}

resource "google_compute_managed_ssl_certificate" "main" {
  name = "kanea-managed-cert${local.name_suffix}"

  managed {
    domains = [var.domain, "www.${var.domain}"]
  }
}

resource "google_compute_target_https_proxy" "main" {
  name             = "kanea-https-proxy${local.name_suffix}"
  url_map          = google_compute_url_map.main.id
  ssl_certificates = [google_compute_managed_ssl_certificate.main.id]
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
