variable "vkcs_username" {
  type      = string
  sensitive = true
}

variable "vkcs_password" {
  type      = string
  sensitive = true
}

variable "vkcs_project_id" {
  type = string
}

variable "vkcs_user_domain_name" {
  type    = string
  default = "service-users"
}

variable "api_allowed_cidrs" {
  type    = list(string)
  default = []
}

variable "gpu_enabled" {
  type    = bool
  default = false
}

variable "gpu_flavor" {
  description = "Конфигурация ВМ с GPU из консоли VK Cloud; нужна только при gpu_enabled = true"
  type        = string
  default     = ""

  validation {
    condition     = !var.gpu_enabled || var.gpu_flavor != ""
    error_message = "При gpu_enabled = true укажите gpu_flavor."
  }
}

variable "kubeconfig_path" {
  description = "kubeconfig с токеном platform-admin; до создания кластера модуль monitoring не применяют"
  type        = string
  default     = "~/.kube/credit-scoring-stage-admin.yaml"
}

variable "telegram_bot_token" {
  type      = string
  sensitive = true
}

variable "telegram_chat_id" {
  type = string
}
