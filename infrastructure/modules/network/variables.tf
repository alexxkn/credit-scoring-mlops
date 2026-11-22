variable "name" {
  description = "Префикс имён ресурсов окружения"
  type        = string
}

variable "nodes_cidr" {
  description = "Подсеть узлов Kubernetes и балансировщиков"
  type        = string
  default     = "10.10.0.0/24"
}

variable "external_network_name" {
  description = "Внешняя сеть VK Cloud для выхода в интернет"
  type        = string
  default     = "internet"
}

variable "dns_nameservers" {
  type    = list(string)
  default = ["8.8.8.8", "8.8.4.4"]
}
