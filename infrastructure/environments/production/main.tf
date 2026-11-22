locals {
  name        = "credit-scoring-prod"
  environment = "production"
  pods_cidr   = "10.100.0.0/16"
}

module "network" {
  source     = "../../modules/network"
  name       = local.name
  nodes_cidr = "10.10.0.0/24"
}

module "kubernetes" {
  source              = "../../modules/kubernetes"
  name                = local.name
  environment         = local.environment
  network_id          = module.network.network_id
  subnet_id           = module.network.subnet_id
  external_network_id = module.network.external_network_id
  pods_cidr           = local.pods_cidr
  api_allowed_cidrs   = var.api_allowed_cidrs

  node_groups = {
    # Разные типы инстансов: app под поды API (масштабируется по нагрузке), system под мониторинг, Airflow и MLflow
    "app"    = { flavor = "STD3-4-8", zone = "MS1", min_size = 2, max_size = 6, disk_size = 40 }
    "system" = { flavor = "STD3-4-16", zone = "MS1", min_size = 1, max_size = 2, disk_size = 60 }
  }

  gpu_node_group = {
    enabled  = var.gpu_enabled
    flavor   = var.gpu_flavor
    zone     = "MS1"
    max_size = 1
  }

  depends_on = [module.network]
}

module "storage" {
  source        = "../../modules/storage"
  name          = local.name
  bucket_prefix = "mifirobo-prod"
  network_id    = module.network.network_id
  subnet_id     = module.network.subnet_id
  allowed_cidrs = [module.network.subnet_cidr, local.pods_cidr]

  depends_on = [module.network]
}

module "monitoring" {
  source             = "../../modules/monitoring"
  telegram_bot_token = var.telegram_bot_token
  telegram_chat_id   = var.telegram_chat_id
  loki_bucket        = module.storage.buckets["loki"]
  s3_access_key      = module.storage.s3_access_key
  s3_secret_key      = module.storage.s3_secret_key
  dashboards_dir     = "${path.root}/../../../deployment/monitoring/dashboards"

  depends_on = [module.kubernetes]
}
