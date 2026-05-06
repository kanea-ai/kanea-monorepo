output "lb_ip" {
  value       = google_compute_global_address.lb.address
  description = "Anycast IP for the global external Application LB."
}

output "cloud_run_urls" {
  value = { for k, s in google_cloud_run_v2_service.svc : k => s.uri }
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

# Values the GitHub Actions workflow needs. Set as repo-level Actions Variables
# (not secrets — these aren't sensitive) on the kanea-ai/kanea-monorepo repo.
output "wif_provider" {
  value       = google_iam_workload_identity_pool_provider.github.name
  description = "Full WIF provider resource name. Use as `workload_identity_provider` in google-github-actions/auth."
}

output "wif_service_account" {
  value       = google_service_account.github_deployer.email
  description = "Service account the workflow impersonates via WIF."
}
