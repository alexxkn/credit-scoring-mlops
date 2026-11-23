#!/bin/bash
# Seldon Core operator и SeldonDeployment с предикторами main, challenger и shadow
set -euo pipefail

readonly SELDON_VERSION="1.17.1"

cd "$(dirname "$0")"
helm repo add seldonio https://storage.googleapis.com/seldon-charts > /dev/null
helm repo update seldonio > /dev/null
helm upgrade --install seldon-core seldonio/seldon-core-operator --version "${SELDON_VERSION}" -n seldon-system --create-namespace \
  -f operator-values.yaml --wait --timeout 10m
kubectl apply -f seldondeployment.yaml
