# Connect Alertmanager

The setup page supports three installation styles. Choose the one used by your cluster, download the generated artifact, and apply it with the command shown on the page.

## Plain Deployment

Download the Kustomize bundle, merge its `receiver.yaml` into the active Alertmanager configuration, and run `kubectl apply -k .`. It creates a Secret and mounts it read-only. The bundle assumes an `alertmanager` Deployment in the `monitoring` namespace; a plain Deployment cannot safely merge an unknown existing ConfigMap automatically.

## Helm

Download the values file and pass it to your chart with `-f alertmanager-values.yaml`. The values mount the Secret at a fixed path and configure `credentials_file` instead of putting the token in Alertmanager's configuration.

## Prometheus Operator

Download the `AlertmanagerConfig` manifest and run `kubectl apply -f alertmanagerconfig.yaml`. It creates the Secret and references it from the receiver using the Operator's secret reference.

## Verify delivery

Send a test firing alert, then open **Investigations**. A received alert should appear as a pending or completed investigation. Use **Revoke** in Settings to immediately invalidate the token.
