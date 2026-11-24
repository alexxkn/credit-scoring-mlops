#!/bin/bash
# Ждёт, пока Flagger закончит анализ новой ревизии: Succeeded — выкатка прошла, Failed — откат уже выполнен
set -euo pipefail

readonly NAMESPACE="$1"
readonly CANARY="${2:-credit-scoring-api}"
readonly TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-1500}"
# Flagger проверяет canary раз в минуту: если за три интервала статус не сменился, новой ревизии нет
readonly NO_REVISION_SECONDS=180

# Вердикт засчитывается, только если статус сменился после начала ожидания, иначе это результат прошлой выкатки
started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
deadline=$((SECONDS + TIMEOUT_SECONDS))
while ((SECONDS < deadline)); do
  status="$(kubectl -n "${NAMESPACE}" get canary "${CANARY}" -o jsonpath='{.status.phase} {.status.lastTransitionTime} {.status.canaryWeight}')"
  read -r phase transition weight <<< "${status}"
  echo "$(date +%T) phase=${phase} weight=${weight:-0} transition=${transition}"
  if [[ "${transition}" > "${started}" || "${transition}" == "${started}" ]]; then
    case "${phase}" in
      Succeeded | Initialized)
        exit 0
        ;;
      Failed)
        kubectl -n "${NAMESPACE}" describe canary "${CANARY}" | tail -20 >&2
        exit 1
        ;;
    esac
  elif ((SECONDS > NO_REVISION_SECONDS)) && [[ "${phase}" == Succeeded || "${phase}" == Initialized ]]; then
    echo "Новой ревизии нет, в работе прежняя версия"
    exit 0
  fi
  sleep 15
done
echo "Flagger не закончил анализ за ${TIMEOUT_SECONDS} с" >&2
exit 1
