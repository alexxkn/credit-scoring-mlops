terraform {
  required_providers {
    vkcs = { source = "vk-cs/vkcs" }
  }
}

data "vkcs_compute_flavor" "master" {
  name = var.master_flavor
}

data "vkcs_compute_flavor" "node" {
  for_each = var.node_groups
  name     = each.value.flavor
}

data "vkcs_compute_flavor" "gpu" {
  count = var.gpu_node_group.enabled ? 1 : 0
  name  = var.gpu_node_group.flavor
}

resource "vkcs_kubernetes_cluster_v2" "this" {
  name                   = var.name
  description            = "Credit scoring ${var.environment}"
  version                = var.kubernetes_version
  cluster_type           = "standard"
  master_count           = 1
  availability_zones     = [var.master_zone]
  master_flavor          = data.vkcs_compute_flavor.master.id
  network_id             = var.network_id
  subnet_id              = var.subnet_id
  loadbalancer_subnet_id = var.subnet_id
  external_network_id    = var.external_network_id
  public_ip              = true
  network_plugin         = "calico"
  pods_ipv4_cidr         = var.pods_cidr
  # Пустой список открывает API всем; для production сюда кладут адреса офиса и раннеров CI
  loadbalancer_allowed_cidrs = var.api_allowed_cidrs
  labels                     = { environment = var.environment }
}

# CPU-группы узлов. Кластер standard живёт в одной зоне, узлы тоже; несколько зон даёт только regional-кластер с тремя мастерами
resource "vkcs_kubernetes_node_group_v2" "cpu" {
  for_each               = var.node_groups
  cluster_id             = vkcs_kubernetes_cluster_v2.this.id
  name                   = each.key
  node_flavor            = data.vkcs_compute_flavor.node[each.key].id
  availability_zone      = each.value.zone
  scale_type             = "auto_scale"
  auto_scale_min_size    = each.value.min_size
  auto_scale_max_size    = each.value.max_size
  parallel_upgrade_chunk = 30
  disk_type              = var.disk_type
  disk_size              = each.value.disk_size
  labels                 = { "node-role.credit-scoring/type" = "cpu", "node-role.credit-scoring/pool" = each.key }
}

# GPU-группа включается переменной: в проекте пока нет GPU-конфигураций, по замерам модели GPU не нужен
resource "vkcs_kubernetes_node_group_v2" "gpu" {
  count                  = var.gpu_node_group.enabled ? 1 : 0
  cluster_id             = vkcs_kubernetes_cluster_v2.this.id
  name                   = "gpu"
  node_flavor            = data.vkcs_compute_flavor.gpu[0].id
  availability_zone      = var.gpu_node_group.zone
  scale_type             = "auto_scale"
  auto_scale_min_size    = 0
  auto_scale_max_size    = var.gpu_node_group.max_size
  parallel_upgrade_chunk = 50
  disk_type              = var.disk_type
  disk_size              = 100
  labels                 = { "node-role.credit-scoring/type" = "gpu" }
  taints = [{
    key    = "nvidia.com/gpu"
    value  = "present"
    effect = "NoSchedule"
  }]
}

# Политики безопасности Gatekeeper. hostfilesystem и hostnamespace VK Cloud включает при создании кластера, здесь они импортированы:
# node-exporter читает /proc и /sys хоста, поэтому namespace мониторинга исключён, для остальных запрет остаётся
data "vkcs_kubernetes_security_policy_template_v2" "this" {
  for_each = toset(["k8spsphostfilesystem", "k8spsphostnamespace", "k8sblocknodeport"])
  name     = each.value
  version  = "1.0.0"
}

resource "vkcs_kubernetes_security_policy_v2" "host_filesystem" {
  cluster_id                  = vkcs_kubernetes_cluster_v2.this.id
  security_policy_template_id = data.vkcs_kubernetes_security_policy_template_v2.this["k8spsphostfilesystem"].id
  namespace                   = "*"
  policy_settings = jsonencode({
    allowedHostPaths = [
      { pathPrefix = "/psp", readOnly = true },
      { pathPrefix = "/etc/machine-id", readOnly = true },
      { pathPrefix = "/usr/share/zoneinfo", readOnly = true },
    ]
    excludedNamespaces = var.host_access_namespaces
  })
}

resource "vkcs_kubernetes_security_policy_v2" "host_namespace" {
  cluster_id                  = vkcs_kubernetes_cluster_v2.this.id
  security_policy_template_id = data.vkcs_kubernetes_security_policy_template_v2.this["k8spsphostnamespace"].id
  namespace                   = "*"
  policy_settings             = jsonencode({ excludedNamespaces = var.host_access_namespaces })
}

# Сервисы наружу только через балансировщик Istio, NodePort запрещён во всех namespace
resource "vkcs_kubernetes_security_policy_v2" "block_node_port" {
  cluster_id                  = vkcs_kubernetes_cluster_v2.this.id
  security_policy_template_id = data.vkcs_kubernetes_security_policy_template_v2.this["k8sblocknodeport"].id
  namespace                   = "*"
  policy_settings             = jsonencode({ excludedNamespaces = [] })
}
