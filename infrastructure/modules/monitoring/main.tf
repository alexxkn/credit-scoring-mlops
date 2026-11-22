terraform {
  required_providers {
    helm       = { source = "hashicorp/helm" }
    kubernetes = { source = "hashicorp/kubernetes" }
    random     = { source = "hashicorp/random" }
  }
}

locals {
  system_node_selector = jsonencode({ "node-role.credit-scoring/pool" = "system" })
}

resource "random_password" "grafana" {
  length  = 20
  special = false
}

resource "helm_release" "kube_prometheus_stack" {
  name       = "kube-prometheus-stack"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  version    = var.chart_versions.kube_prometheus_stack
  namespace  = var.namespace
  timeout    = 900
  # namespace monitoring VK Cloud создаёт вместе с кластером, в другом кластере его создаст helm
  create_namespace = true

  values = [templatefile("${path.module}/values/kube-prometheus-stack.yaml.tftpl", {
    namespace              = var.namespace
    system_node_selector   = local.system_node_selector
    telegram_bot_token     = var.telegram_bot_token
    telegram_chat_id       = var.telegram_chat_id
    grafana_admin_password = random_password.grafana.result
    rules                  = file("${path.module}/values/alert-rules.yaml")
  })]
}

resource "kubernetes_config_map_v1" "loki_rules" {
  metadata {
    name      = "loki-rules"
    namespace = var.namespace
  }
  data = { "credit-scoring.yaml" = file("${path.module}/values/loki-rules.yaml") }
}

resource "helm_release" "loki" {
  name       = "loki"
  repository = "https://grafana.github.io/helm-charts"
  chart      = "loki"
  version    = var.chart_versions.loki
  namespace  = var.namespace
  timeout    = 900

  values = [templatefile("${path.module}/values/loki.yaml.tftpl", {
    namespace            = var.namespace
    system_node_selector = local.system_node_selector
    bucket               = var.loki_bucket
    s3_endpoint          = var.s3_endpoint
    s3_access_key        = var.s3_access_key
    s3_secret_key        = var.s3_secret_key
  })]

  depends_on = [helm_release.kube_prometheus_stack, kubernetes_config_map_v1.loki_rules]
}

resource "helm_release" "alloy" {
  name       = "alloy"
  repository = "https://grafana.github.io/helm-charts"
  chart      = "alloy"
  version    = var.chart_versions.alloy
  namespace  = var.namespace

  values     = [templatefile("${path.module}/values/alloy.yaml.tftpl", { namespace = var.namespace })]
  depends_on = [helm_release.loki]
}

resource "helm_release" "pushgateway" {
  name       = "pushgateway"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "prometheus-pushgateway"
  version    = var.chart_versions.pushgateway
  namespace  = var.namespace

  values = [yamlencode({
    nodeSelector   = jsondecode(local.system_node_selector)
    serviceMonitor = { enabled = true, namespace = var.namespace }
  })]
  depends_on = [helm_release.kube_prometheus_stack]
}

# Дашборды Grafana: sidecar подхватывает ConfigMap с меткой grafana_dashboard
resource "kubernetes_config_map_v1" "dashboards" {
  for_each = fileset(var.dashboards_dir, "*.json")
  metadata {
    name      = "dashboard-${trimsuffix(each.value, ".json")}"
    namespace = var.namespace
    labels    = { grafana_dashboard = "1" }
  }
  data       = { (each.value) = file("${var.dashboards_dir}/${each.value}") }
  depends_on = [helm_release.kube_prometheus_stack]
}
