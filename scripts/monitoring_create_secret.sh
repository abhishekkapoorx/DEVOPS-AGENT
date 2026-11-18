#!/usr/bin/env bash
set -euo pipefail

: "${WEBHOOK_TOKEN:?Set WEBHOOK_TOKEN before creating the monitoring Secret}"
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
kubectl -n monitoring create secret generic incident-webhook-token --from-literal="token=${WEBHOOK_TOKEN}" --dry-run=client -o yaml | kubectl apply -f -
