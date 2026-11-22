#!/bin/bash
# Ждёт, пока Flagger закончит анализ новой ревизии: Succeeded — выкатка прошла, Failed — откат уже выполнен
set -euo pipefail

readonly NAMESPACE="$1"
readonly CANARY="${2:-credit-scoring-api}"
readonly TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-1500}"

# Flagger меняет статус не сразу после apply, без паузы можно прочитать вердикт прошлой выкатки
sleep 20
deadline=$((SECONDS + TIMEOUT_SECONDS))
while ((SECONDS < deadline)); do
  phase="$(kubectl -n "${NAMESPACE}" get canary "${CANARY}" -o jsonpath='{.status.phase}')"
  weight="$(kubectl -n "${NAMESPACE}" get canary "${CANARY}" -o jsonpath='{.status.canaryWeight}')"
  echo "$(date +%T) phase=${phase} weight=${weight:-0}"
  case "${phase}" in
    Succeeded | Initialized)
      exit 0
      ;;
    Failed)
      kubectl -n "${NAMESPACE}" describe canary "${CANARY}" | tail -20 >&2
      exit 1
      ;;
  esac
  sleep 15
done
echo "Flagger не закончил анализ за ${TIMEOUT_SECONDS} с" >&2
exit 1
