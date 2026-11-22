#!/bin/bash
# Нагрузочный тест образа backend при разных лимитах CPU: имитирует поды на разных конфигурациях узлов
set -euo pipefail

readonly DOCKER="${DOCKER:-docker}"
readonly IMAGE="${IMAGE:-credit-scoring-backend:dev}"
readonly DURATION="${DURATION:-60s}"
readonly USERS="${USERS:-200}"
readonly OUT_DIR="reports/load_test"

cd "$(dirname "$0")/.."
mkdir -p "${OUT_DIR}"
for cpus in 1 2 4; do
  # Сеть хоста: проброс портов rootless-контейнера сам упирается в CPU и искажает замер
  "${DOCKER}" run -d --rm --name "loadtest-${cpus}" --cpus "${cpus}" --network host "${IMAGE}" \
    uvicorn src.api.app:app --host 127.0.0.1 --port 18080 --no-access-log --workers "${cpus}" > /dev/null
  until curl -sf http://127.0.0.1:18080/ready > /dev/null; do sleep 0.5; done
  locust -f loadtest/locustfile.py --headless --users "${USERS}" --processes 8 --spawn-rate 100 --run-time "${DURATION}" \
    --host http://127.0.0.1:18080 --csv "${OUT_DIR}/cpu${cpus}" --only-summary > /dev/null 2>&1
  "${DOCKER}" rm -f "loadtest-${cpus}" > /dev/null
done
