#!/bin/bash
# Собирает образ с API, запускает контейнер и отправляет тестовый запрос
set -euo pipefail
cd "$(dirname "$0")/.."

# Команду берём из переменной, потому что локально у меня podman (DOCKER=podman), но по заданию по умолчанию docker
readonly DOCKER="${DOCKER:-docker}"

"${DOCKER}" build -t credit-scoring-api .
if "${DOCKER}" container inspect credit-scoring-api > /dev/null 2>&1; then
  "${DOCKER}" rm -f credit-scoring-api
fi
"${DOCKER}" run -d --name credit-scoring-api -p 8000:8000 credit-scoring-api

# Модель загружается несколько секунд, ждём, пока API начнёт отвечать
for _ in $(seq 30); do
  curl -sf http://127.0.0.1:8000/ > /dev/null && break
  sleep 1
done

curl -s -X POST http://127.0.0.1:8000/predict -H "Content-Type: application/json" -d '{
  "LIMIT_BAL": 50000, "SEX": 2, "EDUCATION": 2, "MARRIAGE": 1, "AGE": 30,
  "PAY_0": 2, "PAY_2": 2, "PAY_3": 0, "PAY_4": 0, "PAY_5": 0, "PAY_6": 0,
  "BILL_AMT1": 48000, "BILL_AMT2": 47000, "BILL_AMT3": 46000, "BILL_AMT4": 45000, "BILL_AMT5": 44000, "BILL_AMT6": 43000,
  "PAY_AMT1": 0, "PAY_AMT2": 1500, "PAY_AMT3": 1500, "PAY_AMT4": 1500, "PAY_AMT5": 1500, "PAY_AMT6": 1500
}'
echo
