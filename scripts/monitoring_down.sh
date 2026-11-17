#!/usr/bin/env bash
set -euo pipefail
helm uninstall monitoring --namespace monitoring
kubectl delete -f deploy/monitoring/prometheus-rules.yaml --ignore-not-found
kubectl delete -f deploy/monitoring/rbac-readonly.yaml --ignore-not-found
kubectl delete secret incident-webhook-token -n monitoring --ignore-not-found
