#!/bin/bash
# Критические алерты Prometheus по namespace: запрос через API-proxy Kubernetes, без доступа к Prometheus снаружи
set -euo pipefail

readonly NAMESPACE="$1"
readonly PROMETHEUS="/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query"

query="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "ALERTS{alertstate=\"firing\",severity=\"critical\",namespace=\"${NAMESPACE}\"}")"
firing="$(kubectl get --raw "${PROMETHEUS}?query=${query}" | python3 -c 'import json, sys; print(len(json.load(sys.stdin)["data"]["result"]))')"
echo "критических алертов в ${NAMESPACE}: ${firing}"
if ((firing > 0)); then
  kubectl get --raw "${PROMETHEUS}?query=${query}" >&2
  exit 1
fi
