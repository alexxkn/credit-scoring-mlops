#!/bin/bash
# ML-платформа в namespace mlops: MLflow и Airflow. Пароли БД и ключи S3 берутся из outputs Terraform
set -euo pipefail

readonly AIRFLOW_CHART_VERSION="1.22.0"
readonly NAMESPACE="mlops"
readonly TF="../../infrastructure/scripts/tf.sh"

cd "$(dirname "$0")"
postgres_host="$("${TF}" production output -raw postgres_host)"
s3_access_key="$("${TF}" production output -raw s3_access_key)"
s3_secret_key="$("${TF}" production output -raw s3_secret_key)"
mlflow_password="$("${TF}" production output -json database_passwords | python3 -c 'import json,sys; print(json.load(sys.stdin)["mlflow"])')"
airflow_password="$("${TF}" production output -json database_passwords | python3 -c 'import json,sys; print(json.load(sys.stdin)["airflow"])')"

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "${NAMESPACE}" create secret generic mlops-s3 --dry-run=client -o yaml \
  --from-literal=AWS_ACCESS_KEY_ID="${s3_access_key}" --from-literal=AWS_SECRET_ACCESS_KEY="${s3_secret_key}" | kubectl apply -f -
kubectl -n "${NAMESPACE}" create secret generic mlflow --dry-run=client -o yaml \
  --from-literal=MLFLOW_BACKEND_URI="postgresql://mlflow:${mlflow_password}@${postgres_host}:5432/mlflow" \
  --from-literal=AWS_ACCESS_KEY_ID="${s3_access_key}" --from-literal=AWS_SECRET_ACCESS_KEY="${s3_secret_key}" | kubectl apply -f -
kubectl -n "${NAMESPACE}" create secret generic airflow-metadata --dry-run=client -o yaml \
  --from-literal=connection="postgresql://airflow:${airflow_password}@${postgres_host}:5432/airflow" | kubectl apply -f -

kubectl -n "${NAMESPACE}" apply -f mlflow.yaml
kubectl apply -f rbac.yaml

helm repo add apache-airflow https://airflow.apache.org > /dev/null
helm repo update apache-airflow > /dev/null
# Пароль администратора Airflow задаётся при установке и в репозиторий не попадает
helm upgrade --install airflow apache-airflow/airflow --version "${AIRFLOW_CHART_VERSION}" -n "${NAMESPACE}" -f airflow-values.yaml \
  --set createUserJob.defaultUser.password="${AIRFLOW_ADMIN_PASSWORD:?задайте AIRFLOW_ADMIN_PASSWORD}" --timeout 15m --wait
