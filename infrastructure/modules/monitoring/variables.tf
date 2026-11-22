variable "namespace" {
  type    = string
  default = "monitoring"
}

variable "telegram_bot_token" {
  type      = string
  sensitive = true
}

variable "telegram_chat_id" {
  type = string
}

variable "loki_bucket" {
  type = string
}

variable "s3_endpoint" {
  type    = string
  default = "https://hb.ru-msk.vkcloud-storage.ru"
}

variable "s3_access_key" {
  type      = string
  sensitive = true
}

variable "s3_secret_key" {
  type      = string
  sensitive = true
}

variable "dashboards_dir" {
  description = "Каталог с JSON-дашбордами Grafana"
  type        = string
}

variable "chart_versions" {
  type = object({
    kube_prometheus_stack = string
    loki                  = string
    alloy                 = string
    pushgateway           = string
  })
  default = {
    kube_prometheus_stack = "93.9.0"
    loki                  = "7.7.0"
    alloy                 = "1.16.0"
    pushgateway           = "3.11.2"
  }
}
