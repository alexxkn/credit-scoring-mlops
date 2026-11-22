variable "name" {
  type = string
}

variable "network_id" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "allowed_cidrs" {
  description = "Откуда разрешён доступ к PostgreSQL: подсеть узлов и сеть подов"
  type        = list(string)
}

variable "zone" {
  type    = string
  default = "MS1"
}

variable "db_flavor" {
  description = "Минимум для PostgreSQL в VK Cloud: 2 vCPU и 8 ГБ"
  type        = string
  default     = "STD2-2-8"
}

variable "db_volume_size" {
  type    = number
  default = 20
}

variable "postgres_version" {
  type    = string
  default = "16"
}

variable "databases" {
  type    = list(string)
  default = ["mlflow", "airflow"]
}

variable "buckets" {
  type    = list(string)
  default = ["mlflow", "models", "loki", "reports"]
}

variable "bucket_prefix" {
  description = "Имена бакетов глобальные, поэтому префикс уникальный для проекта"
  type        = string
}
