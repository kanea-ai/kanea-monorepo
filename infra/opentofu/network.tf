resource "google_compute_network" "vpc" {
  name                    = "kanea-vpc${local.name_suffix}"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "app" {
  name          = "kanea-app-subnet${local.name_suffix}"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = local.app_subnet_cidr

  private_ip_google_access = true
}

# /28 reserved for the Serverless VPC Access connector.
resource "google_compute_subnetwork" "vpc_connector" {
  name          = "kanea-vpc-connector-subnet${local.name_suffix}"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = local.vpc_connector_subnet_cidr
}

# Private Service Access range for Cloud SQL.
resource "google_compute_global_address" "private_services" {
  name          = "kanea-private-services${local.name_suffix}"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]
}

resource "google_vpc_access_connector" "main" {
  # `vpc_connector_name` is special-cased in locals because connector names
  # cap at 25 chars (`kanea-vpc-connector-staging` is 27).
  name   = local.vpc_connector_name
  region = var.region

  subnet {
    name = google_compute_subnetwork.vpc_connector.name
  }

  min_instances = 2
  max_instances = 5
  machine_type  = "e2-micro"

  # Match the provider's actual default (e2-micro * max_instances=5 → 500
  # Mbps). Without this, plan shows spurious drift suggesting 300 Mbps and
  # forces replacement, which would briefly drop egress for all Cloud Run
  # services routed through this connector.
  max_throughput = 500
}
