#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "${repo_root}"
: "${WEBHOOK_TOKEN:?Set WEBHOOK_TOKEN before starting monitoring}"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update
helm repo update
./scripts/monitoring_create_secret.sh
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack --version 68.4.0 --namespace monitoring --create-namespace --values deploy/monitoring/values.yaml --wait --timeout 10m
kubectl apply -f deploy/monitoring/prometheus-rules.yaml
kubectl apply -f deploy/monitoring/rbac-readonly.yaml
echo "Monitoring is ready. Alertmanager is expected at port-forward localhost:9093."
