output "grafana_admin_password" {
  value     = random_password.grafana.result
  sensitive = true
}

output "alertmanager_url" {
  value = "http://kube-prometheus-stack-alertmanager.${var.namespace}.svc:9093"
}

output "pushgateway_url" {
  value = "http://pushgateway-prometheus-pushgateway.${var.namespace}.svc:9091"
}
