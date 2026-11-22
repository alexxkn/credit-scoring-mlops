provider "vkcs" {
  username         = var.vkcs_username
  password         = var.vkcs_password
  project_id       = var.vkcs_project_id
  user_domain_name = var.vkcs_user_domain_name
  region           = "RegionOne"
}

provider "aws" {
  # VK Object Storage принимает LocationConstraint ru-msk; провайдер v6 шлёт пустой и получает отказ, поэтому v5
  region                      = "ru-msk"
  skip_credentials_validation = true
  skip_region_validation      = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  s3_use_path_style           = false

  endpoints {
    s3 = "https://hb.ru-msk.vkcloud-storage.ru"
  }
}

# Платформенные helm-релизы ставятся токеном ServiceAccount platform-admin: kubeconfig VK Cloud требует client-keystone-auth
provider "helm" {
  kubernetes = {
    config_path = var.kubeconfig_path
  }
}

provider "kubernetes" {
  config_path = var.kubeconfig_path
}
