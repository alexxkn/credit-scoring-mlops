#!/bin/bash
# Выкатка overlay в кластер и ожидание вердикта Flagger: ./scripts/deploy.sh production 1a2b3c4
set -euo pipefail

readonly ENVIRONMENT="$1"
readonly TAG="$2"
readonly NAMESPACE="credit-scoring-${ENVIRONMENT/production/prod}"
readonly OVERLAY="deployment/kubernetes/overlays/${ENVIRONMENT}"

cd "$(dirname "$0")/.."
# Ключи S3 для загрузки моделей по MODEL_URI приходят из секретов CI и в git не хранятся
kubectl -n "${NAMESPACE}" create secret generic credit-scoring-secrets --dry-run=client -o yaml \
  --from-literal=AWS_ACCESS_KEY_ID="${APP_S3_ACCESS_KEY:?}" --from-literal=AWS_SECRET_ACCESS_KEY="${APP_S3_SECRET_KEY:?}" | kubectl apply -f -

sed -i "s/newTag: .*/newTag: ${TAG}/; s/INGRESS_HOST/${INGRESS_HOST:?}/g" "${OVERLAY}"/*.yaml
kubectl apply -k "${OVERLAY}"
./scripts/wait_canary.sh "${NAMESPACE}"
