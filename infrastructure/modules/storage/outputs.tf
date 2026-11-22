output "postgres_host" {
  value = vkcs_db_instance.postgres.ip[0]
}

output "database_passwords" {
  value     = { for name, password in random_password.db : name => password.result }
  sensitive = true
}

output "s3_access_key" {
  value     = vkcs_iam_s3_account.workloads.access_key
  sensitive = true
}

output "s3_secret_key" {
  value     = vkcs_iam_s3_account.workloads.secret_key
  sensitive = true
}

output "buckets" {
  value = { for key, bucket in aws_s3_bucket.this : key => bucket.bucket }
}
