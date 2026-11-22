#!/bin/bash
# Проверка API после выкатки: сервис отвечает, предсказание в допустимых пределах, неверный запрос отклоняется
set -euo pipefail

readonly BASE_URL="$1"
readonly CLIENT='{"LIMIT_BAL": 50000, "SEX": 2, "EDUCATION": 2, "MARRIAGE": 1, "AGE": 30, "PAY_0": 2, "PAY_2": 2, "PAY_3": 0, "PAY_4": 0, "PAY_5": 0,
  "PAY_6": 0, "BILL_AMT1": 48000, "BILL_AMT2": 47000, "BILL_AMT3": 46000, "BILL_AMT4": 45000, "BILL_AMT5": 44000, "BILL_AMT6": 43000,
  "PAY_AMT1": 0, "PAY_AMT2": 1500, "PAY_AMT3": 1500, "PAY_AMT4": 1500, "PAY_AMT5": 1500, "PAY_AMT6": 1500}'

curl -sf --retry 5 --retry-delay 3 "${BASE_URL}/health" > /dev/null
response="$(curl -sf -X POST "${BASE_URL}/predict" -H 'Content-Type: application/json' -d "${CLIENT}")"
echo "${response}"
python3 -c 'import json, sys; r = json.loads(sys.argv[1]); assert 0 <= r["default_probability"] <= 1 and r["default_prediction"] in (0, 1)' "${response}"
status="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${BASE_URL}/predict" -H 'Content-Type: application/json' -d '{"AGE": 10}')"
if [[ "${status}" != 422 ]]; then
  echo "неверный запрос вернул ${status}, ожидался 422" >&2
  exit 1
fi
