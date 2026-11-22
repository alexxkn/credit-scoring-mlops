#!/bin/bash
# Платформа кластера поверх инфраструктуры Terraform: Istio, Flagger. Мониторинг ставит модуль Terraform monitoring
set -euo pipefail

readonly ISTIO_VERSION="1.30.8"
readonly FLAGGER_VERSION="1.45.0"
readonly LOADTESTER_VERSION="0.39.0"

cd "$(dirname "$0")"
helm repo add istio https://istio-release.storage.googleapis.com/charts > /dev/null
helm repo add flagger https://flagger.app > /dev/null
helm repo update istio flagger > /dev/null

helm upgrade --install istio-base istio/base --version "${ISTIO_VERSION}" -n istio-system --create-namespace --wait
helm upgrade --install istiod istio/istiod --version "${ISTIO_VERSION}" -n istio-system -f istiod.yaml --wait
helm upgrade --install istio-ingressgateway istio/gateway --version "${ISTIO_VERSION}" -n istio-ingress --create-namespace -f istio-gateway.yaml --wait

helm upgrade --install flagger flagger/flagger --version "${FLAGGER_VERSION}" -n istio-system -f flagger.yaml --wait

for namespace in credit-scoring-staging credit-scoring-prod; do
  kubectl create namespace "${namespace}" --dry-run=client -o yaml | kubectl apply -f -
  kubectl label namespace "${namespace}" istio-injection=enabled --overwrite
  # Генератор нагрузки и приёмочные проверки Flagger во время canary-анализа
  helm upgrade --install flagger-loadtester flagger/loadtester --version "${LOADTESTER_VERSION}" -n "${namespace}" --wait
done

kubectl apply -f gateway.yaml -f istio-monitoring.yaml -f ci-rbac.yaml
