output "cluster_id" {
  value = vkcs_kubernetes_cluster_v2.this.id
}

output "api_address" {
  value = vkcs_kubernetes_cluster_v2.this.api_address
}

output "kubeconfig" {
  value     = vkcs_kubernetes_cluster_v2.this.k8s_config
  sensitive = true
}
