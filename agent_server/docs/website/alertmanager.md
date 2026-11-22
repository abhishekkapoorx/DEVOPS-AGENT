# Connect Alertmanager

Alertmanager delivers firing and resolved alerts to the Investigation Agent's
webhook. The generated integration artifacts configure a bearer token and
keep it in a Kubernetes Secret. Do not place the token in a public repository
or commit a personalized download.

## Configure the integration

1. Sign in to the DevOps Agent website and open **Settings → Integrations**.
2. Create a webhook secret with a recognizable name. Copy the token and
   endpoint immediately; the token is shown only at creation time.
3. Select the artifact for the Alertmanager deployment style:
   - **Plain Deployment:** Kustomize `.zip` bundle.
   - **Helm:** values `.yaml` file.
   - **Prometheus Operator:** `AlertmanagerConfig` and Secret `.yaml` file.
4. Review the artifact for your namespace, deployment, and chart conventions.
   Apply it only after confirming the endpoint and token are correct.
5. Send a test alert and verify that a report appears under **Investigations**.

The authenticated Integrations page generates personalized downloads with the
actual endpoint and token. Revoke the webhook secret on that page to invalidate
it. Recreating a download does not change a token that has already been
revoked.

## Download safe examples

These public examples contain placeholders, not a usable credential. Replace
`YOUR_AGENT_HOST` and `REPLACE_WITH_WEBHOOK_TOKEN` before use. For a real
deployment, prefer the personalized files generated in Settings.

- [Kustomize example bundle](/docs/downloads/alertmanager/kustomize.zip)
- [Helm example values](/docs/downloads/alertmanager/helm.yaml)
- [Prometheus Operator example](/docs/downloads/alertmanager/operator.yaml)

## Plain Deployment with Kustomize

The example bundle contains a Secret, a ConfigMap with the receiver snippet,
and a patch that mounts the Secret read-only. It assumes a Deployment named
`alertmanager` in namespace `monitoring`. Review and adapt those values to
your installation.

The receiver configuration must be merged into the active Alertmanager
configuration. A Kustomize ConfigMap does not automatically replace or merge
an existing configuration. After integrating the receiver, apply the bundle
from its extracted directory:

```bash
kubectl apply -k .
```

Reload or roll out Alertmanager according to your configuration management
process, then verify that its logs show successful webhook delivery.

## Helm

The downloaded values file configures the receiver and mounts the token
through a chart-managed Secret. Chart values differ between distributions;
confirm that your chart supports the `alertmanager.config`,
`alertmanager.extraSecretMounts`, and `alertmanager.secret` values used by the
example before upgrading:

```bash
helm upgrade --install <release> <chart> \
  --namespace monitoring \
  --values alertmanager-webhook-values.yaml
```

Treat customized values files as secrets if they contain the real token.
Prefer the chart's supported secret mechanism and do not commit secret-bearing
values to source control.

## Prometheus Operator

The Operator artifact contains a Secret and an `AlertmanagerConfig` resource.
The cluster must have the Prometheus Operator CRDs installed. The active
Alertmanager must select this resource by namespace and label; configure those
selectors according to the Operator installation before applying:

```bash
kubectl apply -f alertmanagerconfig.yaml
```

Keep the Secret in the namespace expected by the `AlertmanagerConfig` and
verify that the `Alertmanager` resource accepts the config selector.

## Delivery and security checks

- `send_resolved` is enabled so resolved notifications update investigation
  state.
- The public webhook endpoint must be reachable by Alertmanager over HTTPS in
  production. Configure the server's public base URL to match that endpoint.
- Store webhook secrets using the server's configured encrypted secret store;
  `ENCRYPTION_KEY` must be available when creating integrations.
- Limit cluster access to the generated Secret and revoke unused tokens.
- Example downloads are intentionally nonfunctional until placeholders are
  replaced. The Settings downloads are owner-authenticated and expire when the
  server process loses its short-lived artifact record.
