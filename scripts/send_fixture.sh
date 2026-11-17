#!/usr/bin/env bash
set -euo pipefail

fixture_path=${1:?usage: scripts/send_fixture.sh <path>}
webhook_url=${WEBHOOK_URL:-http://127.0.0.1:8000}
headers=(-H 'Content-Type: application/json')
if [[ -n "${WEBHOOK_TOKEN:-}" ]]; then
  headers+=(-H "Authorization: Bearer ${WEBHOOK_TOKEN}")
fi

curl --fail-with-body --silent --show-error \
  --request POST \
  "${headers[@]}" \
  --data-binary "@${fixture_path}" \
  "${webhook_url%/}/webhook/alertmanager"
