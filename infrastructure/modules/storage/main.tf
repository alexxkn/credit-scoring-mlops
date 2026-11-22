terraform {
  required_providers {
    vkcs   = { source = "vk-cs/vkcs" }
    aws    = { source = "hashicorp/aws" }
    random = { source = "hashicorp/random" }
  }
}

# PostgreSQL для метаданных MLflow и Airflow. Доступ только из подсети узлов и сети подов, наружу порт закрыт
resource "vkcs_networking_secgroup" "postgres" {
  name        = "${var.name}-postgres"
  description = "PostgreSQL: 5432 только из кластера"
  # Стандартные правила оставляем: исходящий трафик нужен агенту DBaaS для бэкапов и мониторинга
  delete_default_rules = false
  sdn                  = "sprut"
}

resource "vkcs_networking_secgroup_rule" "postgres_from_cluster" {
  for_each          = toset(var.allowed_cidrs)
  security_group_id = vkcs_networking_secgroup.postgres.id
  direction         = "ingress"
  protocol          = "tcp"
  port_range_min    = 5432
  port_range_max    = 5432
  remote_ip_prefix  = each.value
  sdn               = "sprut"
}

data "vkcs_compute_flavor" "db" {
  name = var.db_flavor
}

resource "vkcs_db_instance" "postgres" {
  name              = "${var.name}-postgres"
  flavor_id         = data.vkcs_compute_flavor.db.id
  size              = var.db_volume_size
  volume_type       = "ceph-ssd"
  availability_zone = var.zone

  datastore {
    type    = "postgresql"
    version = var.postgres_version
  }

  network {
    uuid            = var.network_id
    subnet_id       = var.subnet_id
    security_groups = [vkcs_networking_secgroup.postgres.id]
  }

  disk_autoexpand {
    autoexpand    = true
    max_disk_size = 100
  }
}

resource "vkcs_db_database" "this" {
  for_each = toset(var.databases)
  name     = each.value
  dbms_id  = vkcs_db_instance.postgres.id
}

# DBaaS требует не меньше 16 символов, заглавные, строчные, цифру и спецсимвол
resource "random_password" "db" {
  for_each         = toset(var.databases)
  length           = 24
  min_upper        = 2
  min_lower        = 2
  min_numeric      = 2
  min_special      = 2
  override_special = "-_.~"
}

resource "vkcs_db_user" "this" {
  for_each  = toset(var.databases)
  name      = each.value
  password  = random_password.db[each.value].result
  dbms_id   = vkcs_db_instance.postgres.id
  databases = [vkcs_db_database.this[each.value].name]
}

# Отдельный S3-аккаунт для сервисов кластера, чтобы не раздавать в кластер ключи владельца проекта
resource "vkcs_iam_s3_account" "workloads" {
  name        = "${var.name}-workloads"
  description = "MLflow, Loki, модели и отчёты дрифта"
}

# Бакеты создаются приватными. PutPublicAccessBlock VK Object Storage не поддерживает (501), поэтому приватность задаёт ACL
resource "aws_s3_bucket" "this" {
  for_each = toset(var.buckets)
  bucket   = "${var.bucket_prefix}-${each.value}"
}

resource "aws_s3_bucket_acl" "this" {
  for_each = aws_s3_bucket.this
  bucket   = each.value.id
  acl      = "private"
}
