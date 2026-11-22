# Investigations

An investigation starts when Alertmanager sends an alert to the webhook endpoint. The agent normalizes the alert, gathers deterministic read-only evidence, and stores a report that can be reviewed in the web UI.

The report separates evidence from hypotheses. Every supported claim points back to evidence, and degraded runs still retain the deterministic context pack.

## Connect a cluster

Open **Settings → Integrations**, create a webhook token, and download the installation artifact for your Alertmanager setup.
