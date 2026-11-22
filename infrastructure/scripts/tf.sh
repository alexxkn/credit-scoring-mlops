#!/bin/bash
# Запуск terraform для окружения с ключами VK Cloud из локального файла: ./scripts/tf.sh production plan
set -euo pipefail

readonly ENV_FILE="${VKCS_ENV_FILE:-${HOME}/.config/vkcs/credit-scoring.env}"
readonly ENVIRONMENT="$1"
shift

# В CI переменные TF_VAR_* и AWS_* приходят из секретов GitHub, локально берём их из файла
if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
  export TF_VAR_vkcs_username="${OS_USERNAME}"
  export TF_VAR_vkcs_password="${OS_PASSWORD}"
  export TF_VAR_vkcs_project_id="${OS_PROJECT_ID}"
  export TF_VAR_telegram_bot_token="${TELEGRAM_BOT_TOKEN}"
  export TF_VAR_telegram_chat_id="${TELEGRAM_CHAT_ID}"
fi

cd "$(dirname "$0")/../environments/${ENVIRONMENT}"
terraform "$@"
