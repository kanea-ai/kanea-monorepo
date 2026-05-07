# Staging environment — pre-prod testing.
# Apply with:
#   tofu init -reconfigure -backend-config="prefix=terraform/state/staging"
#   tofu apply -var-file=envs/staging.tfvars
#
# Cost knobs vs prod: zonal Cloud SQL on db-f1-micro, Cloud Run capped at 5
# instances, deletion_protection=false on the SQL instance.
#
# Cloud Armor: deny-all-except `staging_allow_ip`. Override the placeholder
# below with your real /32 (e.g. via -var staging_allow_ip=…) once known —
# the default 203.0.113.42 is RFC 5737 docs space and matches no real host.

environment = "staging"
project_id  = "kanea-prod-env"
region      = "europe-west1"
domain      = "staging.kanea.ai"

db_tier                 = "db-f1-micro"
db_availability_type    = "ZONAL"
db_disk_size            = 10
cloud_run_max_instances = 5

staging_allow_ip = "203.0.113.42/32"
