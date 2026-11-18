# Kind monitoring stack

This deployment uses the pinned `prometheus-community/kube-prometheus-stack` Helm chart (`68.4.0`) with Grafana and node-exporter disabled. Prometheus, Alertmanager, and kube-state-metrics remain enabled with small resource limits for a laptop kind cluster.

The API and worker run in Docker Compose on the host. Alertmanager runs inside kind and reaches the host API through `host.docker.internal:8000`. On Linux kind installations where that hostname is unavailable, replace the webhook URL with the Docker gateway address.

## Start

```bash
export WEBHOOK_TOKEN='local-development-token'
./scripts/monitoring_up.sh
```

The Secret is created from `WEBHOOK_TOKEN`; it is never placed in the Alertmanager ConfigMap or values file. Alertmanager mounts it through `alertmanagerSpec.secrets` and reads the token from a file.

Port-forward Alertmanager for validation:

```bash
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-alertmanager 9093:9093
```

Rules cover CrashLoopBackOff, OOMKilled, image pull failures, no endpoints, pod readiness, deployment replica mismatch, and Redis dependency loss. The latency scenario is fixture-only because the demo does not expose a stable latency metric for this agent to scrape.

Demo `for` durations are 30 seconds. Production alerting should use longer durations and environment-specific thresholds.

## Validation

```bash
./scripts/validate_live.sh 01-crashloop-missing-env
./scripts/validate_live.sh all
```

The live script requires `kubectl`, `curl`, `psql`, a reachable kind cluster, a running API/worker, and a port-forwarded Alertmanager. It is intentionally not a CI test.

The read-only ServiceAccount in `rbac-readonly.yaml` is for an in-cluster worker deployment. The current worker runs through Compose and uses the developer kubeconfig; the collector adapter requires no Kubernetes write permission.
