# Investigation Agent

The Investigation Agent turns Alertmanager firing and resolved alerts into
durable, evidence-backed reports. It collects a bounded set of read-only
Kubernetes evidence, optionally asks a configured language model to form
hypotheses, verifies that each claim is grounded in collected evidence, and
stores the report for review. It does not change cluster resources.

Start with [Connect Alertmanager](/docs/investigations/alertmanager) to configure
alert delivery. A signed-in user can review reports under **Investigations**.

## Processing lifecycle

1. **Receive and authenticate.** Alertmanager sends a webhook to
   `/webhook/alertmanager` with the generated bearer token. The request is
   normalized per alert so a malformed item does not discard other valid
   alerts in the same group.
2. **Persist and deduplicate.** The server stores the alert, associates it with
   an investigation, and records audit events. Repeated delivery of the same
   delivery is idempotent; active alerts with the same fingerprint are
   grouped into one investigation with an occurrence count.
3. **Collect deterministic evidence.** A background worker uses the
   allow-listed Kubernetes collectors to read pod status, recent events,
   current and previous logs, workload rollout details, service endpoints,
   and namespace health. Missing alert labels can make some collectors no-op.
4. **Analyze and verify.** If a model is configured, the agent proposes
   hypotheses and checks claim citations against the collected evidence.
   Unverifiable claims are dropped. If model analysis is unavailable or
   fails, the deterministic context pack is still retained and the report is
   marked degraded.
5. **Persist and present.** The report, evidence summaries, run metrics, and
   audit events are saved. The web interface and JSON API expose only data
   belonging to the authenticated user.

## Evidence and limits

The current collector set is intentionally read-only and bounded:

| Collector | Evidence collected |
| --- | --- |
| `kubernetes.pod_status` | Pod phase, conditions, container states, restart count, and resources. |
| `kubernetes.events` | Up to the 20 most recent matching pod or namespace events. |
| `kubernetes.logs` | Current and previous logs, limited to the latest 200 lines each. |
| `kubernetes.rollout_history` | Deployment template, ReplicaSet revisions, images, environment variable names, resources, and probes. |
| `kubernetes.endpoints` | Service selector and ready/not-ready endpoint counts. |
| `kubernetes.namespace_overview` | Namespace pod totals and non-ready pod summaries. |

The collector registry enforces an allowlist, a per-call timeout, a maximum
number of calls, and a maximum serialized output size. Evidence is redacted
before persistence. Logs, raw alert payloads, and evidence can contain
sensitive operational data; keep access to the service and database limited.

## Report contents and access

A report includes the alert identity and status, occurrence and time metadata,
evidence summaries, and (when available) ranked hypotheses with evidence
references and verification metrics. A degraded report includes a reason and
the deterministic context rather than fabricated analysis.

- Browser: sign in and open **Investigations**.
- JSON list: `GET /v1/investigations`.
- JSON detail: `GET /v1/investigations/{investigation_id}`.

The JSON endpoints require a valid user session. Requests for another user's
investigation return not found. The service currently exposes the report JSON;
it does not provide a separate downloadable report file.

## Developer guide

The implementation is split by responsibility:

- `agent_server/alertmanager.py` validates and normalizes Alertmanager data.
- `agent_server/ingest/service.py` stores alerts, handles deduplication, and
  creates or updates investigations.
- `agent_server/investigations/worker.py` claims queued investigations and
  records completion or retry state.
- `agent_server/investigations/context.py` defines the collector sequence.
- `agent_server/investigations/registry.py` applies allowlist, timeout, output
  bounds, redaction, persistence, and audit behavior.
- `agent_server/tools/collectors/kubernetes_tools.py` implements the
  read-only Kubernetes collectors.
- `agent_server/investigations/runner.py` coordinates collection, analysis,
  persistence, and the optional Slack briefing.
- `agent_server/api/settings.py` serves the authenticated investigation pages
  and JSON API.

Useful focused tests include `tests/test_alertmanager_webhook.py`,
`tests/test_investigation_runner.py`, and `tests/test_settings_pages.py`. When
changing evidence behavior, preserve read-only access, redaction, ownership
checks, degraded-run handling, and audit coverage.

## Troubleshooting

- **No investigation appears:** confirm Alertmanager can reach the public
  webhook URL and that the bearer token is current. Check webhook delivery and
  worker logs.
- **Report is degraded:** inspect the recorded reason. Model configuration is
  optional; Kubernetes evidence can still be collected without model analysis.
- **Evidence is missing:** check that the alert contains useful `namespace`,
  `pod`, `container`, `service`, or workload labels and that the server's
  Kubernetes identity has the necessary read permissions.
- **Manifest downloads fail:** generated, token-bearing installation artifacts
  are available only in the authenticated Integrations flow. See the
  [Alertmanager setup guide](/docs/investigations/alertmanager).
