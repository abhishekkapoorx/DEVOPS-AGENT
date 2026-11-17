#!/usr/bin/env bash
set -euo pipefail

scenario=${1:?usage: scripts/validate_live.sh <scenario|all>}
alertmanager_url=${ALERTMANAGER_URL:-http://127.0.0.1:9093}
database_url=${DATABASE_URL:?Set DATABASE_URL for live validation}
scenario_root="incident-investigation-lab/scenarios"

run_one() {
  local slug=$1
  echo "[live] injecting ${slug}"
  "${scenario_root}/run.sh" "${slug}" inject
  for _ in $(seq 1 60); do
    if curl --fail --silent "${alertmanager_url}/api/v2/alerts" | grep -q "${slug%%-*}"; then break; fi
    sleep 2
  done
  psql "${database_url}" -v ON_ERROR_STOP=1 -c "SELECT status, occurrence_count, slack_posted_at FROM investigations ORDER BY created_at DESC LIMIT 1;"
  "${scenario_root}/run.sh" "${slug}" revert
  echo "[live] ${slug} reverted; verify resolved state separately"
}

if [[ "${scenario}" == "all" ]]; then
  for path in "${scenario_root}"/0*-*/; do run_one "$(basename "${path}")"; done
else
  run_one "${scenario}"
fi
