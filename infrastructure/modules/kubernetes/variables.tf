variable "name" {
  type = string
}

variable "environment" {
  type = string
}

variable "kubernetes_version" {
  type    = string
  default = "v1.35.9"
}

variable "master_flavor" {
  type    = string
  default = "STD3-4-12"
}

variable "master_zone" {
  type    = string
  default = "MS1"
}

variable "network_id" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "external_network_id" {
  type = string
}

variable "pods_cidr" {
  type    = string
  default = "10.100.0.0/16"
}

variable "api_allowed_cidrs" {
  description = "CIDR, которым разрешён доступ к API Kubernetes"
  type        = list(string)
  default     = []
}

variable "disk_type" {
  type    = string
  default = "ceph-ssd"
}

variable "node_groups" {
  description = "CPU-группы узлов с автомасштабированием"
  type = map(object({
    flavor    = string
    zone      = string
    min_size  = number
    max_size  = number
    disk_size = number
  }))
}

variable "gpu_node_group" {
  type = object({
    enabled  = bool
    flavor   = string
    zone     = string
    max_size = number
  })
  default = {
    enabled  = false
    flavor   = ""
    zone     = "MS1"
    max_size = 1
  }
}

variable "host_access_namespaces" {
  description = "Namespace, которым политики разрешают доступ к файловой системе и namespace хоста"
  type        = list(string)
  default     = ["monitoring"]
}
