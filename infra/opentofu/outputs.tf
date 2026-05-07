output "environment" {
  value = var.environment
}

output "lb_ip" {
  value       = google_compute_global_address.lb.address
  description = "Anycast IP for the global external Application LB. Point the env's domain at this."
}

output "cloud_run_urls" {
  value = { for k, s in google_cloud_run_v2_service.svc : k => s.uri }
}

output "cloud_run_service_names" {
  value       = local.service_name
  description = "Per-env service names. CD pipeline reads this to know which Cloud Run service to roll an image onto."
}

output "cloudsql_private_ip" {
  value = google_sql_database_instance.main.private_ip_address
}

output "vpc_connector" {
  value = google_vpc_access_connector.main.id
}

output "artifact_registry_path" {
  value       = local.artifact_registry_path
  description = "Base path for image tags: <region>-docker.pkg.dev/<project>/<repo>"
}

# WIF outputs only meaningful in prod (those resources only exist there).
output "wif_provider" {
  value       = local.is_prod ? google_iam_workload_identity_pool_provider.github[0].name : null
  description = "Full WIF provider resource name. Prod-only; staging shares the same provider."
}

output "wif_service_account" {
  value       = local.deployer_sa_email
  description = "Service account the workflow impersonates via WIF (shared across envs)."
}
