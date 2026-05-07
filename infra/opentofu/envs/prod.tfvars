# Production environment.
# Apply with:
#   tofu init -reconfigure -backend-config="prefix=terraform/state"
#   tofu apply -var-file=envs/prod.tfvars

environment = "prod"
project_id  = "kanea-prod-env"
region      = "europe-west1"
domain      = "kanea.ai"

db_tier                 = "db-custom-2-7680"
db_availability_type    = "REGIONAL"
db_disk_size            = 50
cloud_run_max_instances = 20

google_oauth_client_id = "448296797623-5m87dih7iam21knl9kqgorj91tar3rhl.apps.googleusercontent.com"
github_oauth_client_id = "Ov23lisrnCjhOO0LoecR"
