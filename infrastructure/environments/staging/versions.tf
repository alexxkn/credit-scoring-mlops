terraform {
  required_version = ">= 1.10"

  required_providers {
    vkcs       = { source = "vk-cs/vkcs", version = "~> 0.15" }
    aws        = { source = "hashicorp/aws", version = "~> 5.0" }
    random     = { source = "hashicorp/random", version = "~> 3.6" }
    helm       = { source = "hashicorp/helm", version = "~> 3.0" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.38" }
  }

  # State в Object Storage VK Cloud; ключи берутся из AWS_ACCESS_KEY_ID и AWS_SECRET_ACCESS_KEY
  backend "s3" {
    bucket                      = "mifirobo"
    key                         = "terraform/staging/terraform.tfstate"
    region                      = "ru-msk"
    endpoints                   = { s3 = "https://hb.ru-msk.vkcloud-storage.ru" }
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
    use_lockfile                = true
  }
}
