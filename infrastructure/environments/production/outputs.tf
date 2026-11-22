output "cluster_id" {
  value = module.kubernetes.cluster_id
}

output "api_address" {
  value = module.kubernetes.api_address
}

output "kubeconfig" {
  value     = module.kubernetes.kubeconfig
  sensitive = true
}

output "postgres_host" {
  value = module.storage.postgres_host
}

output "buckets" {
  value = module.storage.buckets
}

output "database_passwords" {
  value     = module.storage.database_passwords
  sensitive = true
}

output "s3_access_key" {
  value     = module.storage.s3_access_key
  sensitive = true
}

output "s3_secret_key" {
  value     = module.storage.s3_secret_key
  sensitive = true
}

output "grafana_admin_password" {
  value     = module.monitoring.grafana_admin_password
  sensitive = true
}
