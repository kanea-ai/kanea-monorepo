resource "google_compute_network" "vpc" {
  name                    = "kanea-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "app" {
  name          = "kanea-app-subnet"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.10.0.0/24"

  private_ip_google_access = true
}

# /28 reserved for the Serverless VPC Access connector.
resource "google_compute_subnetwork" "vpc_connector" {
  name          = "kanea-vpc-connector-subnet"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.10.8.0/28"
}

# Private Service Access range for Cloud SQL.
resource "google_compute_global_address" "private_services" {
  name          = "kanea-private-services"
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
  name   = "kanea-vpc-connector"
  region = var.region

  subnet {
    name = google_compute_subnetwork.vpc_connector.name
  }

  min_instances = 2
  max_instances = 5
  machine_type  = "e2-micro"
}
