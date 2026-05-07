resource "random_password" "db" {
  length  = 32
  special = true
}

resource "google_sql_database_instance" "main" {
  name             = "kanea-pg-15${local.name_suffix}"
  region           = var.region
  database_version = "POSTGRES_15"

  depends_on = [google_service_networking_connection.private_vpc]

  settings {
    tier              = var.db_tier
    availability_type = var.db_availability_type
    disk_type         = "PD_SSD"
    disk_size         = var.db_disk_size
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.vpc.id
      enable_private_path_for_google_cloud_services = true
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "03:00"
    }

    insights_config {
      query_insights_enabled = true
    }

    maintenance_window {
      day  = 7
      hour = 4
    }
  }

  # Prod is delete-protected; staging isn't (cheaper to recreate from a
  # broken state than to manually unlock and retry).
  deletion_protection = local.is_prod
}

resource "google_sql_database" "app" {
  name     = var.db_name
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "app" {
  name     = var.db_user
  instance = google_sql_database_instance.main.name
  password = random_password.db.result
}
