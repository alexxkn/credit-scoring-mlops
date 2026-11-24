#!/bin/bash
# Нагрузочный тест production в облаке: Locust в поде кластера идёт через ingress gateway, HPA добавляет поды API,
# автомасштабирование группы app добавляет узлы. Результат и ход масштабирования пишутся в reports/load_test/cluster
set -euo pipefail

readonly NAMESPACE="mlops"
readonly USERS="${USERS:-400}"
readonly DURATION="${DURATION:-10m}"
readonly HOST_HEADER="${HOST_HEADER:?нужен хост API, например api.168.113.137.131.nip.io}"
readonly IMAGE="ghcr.io/alexxkn/credit-scoring-mlops/trainer:latest"
readonly OUT_DIR="reports/load_test/cluster"

cd "$(dirname "$0")/.."
mkdir -p "${OUT_DIR}"
kubectl -n "${NAMESPACE}" create configmap locustfile --from-file=loadtest/locustfile.py --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "${NAMESPACE}" delete job cluster-loadtest --ignore-not-found
kubectl -n "${NAMESPACE}" apply -f - << EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: cluster-loadtest
spec:
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      nodeSelector:
        node-role.credit-scoring/pool: system
      containers:
        - name: locust
          image: ${IMAGE}
          workingDir: /app
          command: [sh, -c]
          args:
            - pip install -q --target /tmp/pkgs locust==2.47.0 && PYTHONPATH=/app:/tmp/pkgs python -m locust -f /loadtest/locustfile.py --headless
              --users ${USERS} --spawn-rate 20 --processes 3 --run-time ${DURATION} --host http://istio-ingressgateway.istio-ingress
              --csv /tmp/cluster --only-summary --exit-code-on-error 0 && cat /tmp/cluster_stats.csv
          env:
            - name: HOST_HEADER
              value: ${HOST_HEADER}
            - name: CLIENTS_PATH
              value: /app/data/processed/test.csv
          resources:
            requests: {cpu: "3", memory: 2Gi}
            limits: {memory: 2Gi}
          volumeMounts:
            - name: locustfile
              mountPath: /loadtest
      volumes:
        - name: locustfile
          configMap:
            name: locustfile
EOF

# Пока идёт тест, раз в 30 секунд записываем число подов API, нагрузку HPA и узлы
kubectl -n "${NAMESPACE}" wait --for=condition=Ready pod -l job-name=cluster-loadtest --timeout=300s
while ! kubectl -n "${NAMESPACE}" wait --for=condition=complete job/cluster-loadtest --timeout=30s > /dev/null 2>&1; do
  {
    date +%T
    kubectl -n credit-scoring-prod get hpa credit-scoring-api-primary --no-headers
    kubectl get nodes --no-headers
  } >> "${OUT_DIR}/scaling.log"
  if kubectl -n "${NAMESPACE}" get job cluster-loadtest -o jsonpath='{.status.failed}' | grep -q 1; then
    kubectl -n "${NAMESPACE}" logs job/cluster-loadtest
    exit 1
  fi
done
kubectl -n "${NAMESPACE}" logs job/cluster-loadtest > "${OUT_DIR}/locust.log"
