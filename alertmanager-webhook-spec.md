## Problem Statement

As the operator of the incident investigation lab, I need the root FastAPI/Postgres backend to accept Alertmanager webhook notifications so that every alert can enter the read-only incident investigation flow without coupling webhook transport to future deduplication or investigation execution.

## Solution

Add `POST /webhook/alertmanager` to the root backend. It accepts Alertmanager webhook v4 payloads, validates the version, persists the raw webhook for audit, normalizes every valid alert into one internal `NormalizedAlert` shape, skips and logs malformed individual alerts without losing the rest, and hands accepted alerts to an asynchronous ingestion seam. The initial ingestion implementation is a placeholder: it logs accepted alerts and returns `IngestResult` values without deduplicating, creating investigations, calling an LLM, calling Kubernetes, or using a queue.

## User Stories

1. As Alertmanager, I want to POST a v4 webhook payload, so that firing and resolved alerts can enter the incident investigation backend.
2. As the webhook endpoint, I want to validate the Alertmanager version, so that unsupported payload contracts fail clearly.
3. As an operator, I want unsupported versions rejected with HTTP 422, so that compatibility problems are visible.
4. As Alertmanager, I want a webhook containing multiple alerts accepted in one request, so that grouped notifications are handled efficiently.
5. As the backend, I want malformed individual alerts skipped rather than aborting the whole request, so that valid alerts in the same notification still proceed.
6. As an operator, I want the response to report received, accepted, and skipped counts, so that webhook handling is observable.
7. As the backend, I want each alert normalized into one stable internal schema, so that downstream ingestion does not depend on Alertmanager field details.
8. As an investigator, I want the Alertmanager fingerprint retained when present, so that future deduplication has a stable source identity.
9. As an investigator, I want alert status normalized to firing or resolved, so that lifecycle handling is explicit.
10. As an investigator, I want alert names and severities available with an unknown severity fallback, so that incomplete labels remain usable.
11. As an investigator, I want namespace, workload, pod, container, service, and node extracted best-effort from labels, so that future evidence collection has useful Kubernetes context.
12. As an investigator, I want ReplicaSet and pod hash suffixes removed from workload names, so that alerts for one workload share a stable identity.
13. As an investigator, I want summaries and descriptions copied from annotations with alertname fallbacks, so that incomplete annotations do not produce empty incident descriptions.
14. As an investigator, I want complete label and annotation copies retained, so that normalization does not discard source context.
15. As an auditor, I want original alert data and webhook bodies preserved, so that notifications can be replayed later.
16. As an operator, I want receipt timestamps recorded in UTC, so that event timelines are comparable.
17. As an operator, I want Alertmanager timestamps parsed consistently and zero-time end timestamps represented as absent, so that unresolved alerts do not appear to have ended in year one.
18. As an operator, I want the generator URL retained, so that the originating Prometheus query remains traceable.
19. As a deployment administrator, I want an optional shared bearer token, so that development can run without a token while deployments can authenticate Alertmanager.
20. As a deployment administrator, I want token comparison to be constant-time, so that authentication does not expose avoidable timing information.
21. As an operator, I want unauthorized webhook requests rejected with HTTP 401, so that a configured webhook secret protects ingestion.
22. As an operator, I want oversized webhook bodies rejected with HTTP 413, so that request processing has a bounded memory footprint.
23. As an operator, I want a request ID attached to structured logs, so that one webhook can be traced across validation, persistence, normalization, and ingestion.
24. As an operator, I want logs to avoid secrets and full annotation bodies at info level, so that operational logs do not leak sensitive data.
25. As a future deduplication implementer, I want a typed `ingest_alerts` interface, so that deduplication and investigation creation can be added without changing the webhook contract.
26. As a future investigation implementer, I want ingestion results to distinguish created, deduped, resolved, and ignored actions, so that lifecycle outcomes have a stable contract.
27. As a developer, I want the endpoint to hand off accepted alerts without blocking on investigation work, so that Alertmanager receives a fast 202 response.
28. As a developer, I want scenario fixtures used in endpoint tests, so that the implementation matches the incident investigation lab’s known cases.
29. As a developer, I want focused normalization tests, so that label extraction remains deterministic and easy to extend.
30. As an operator, I want a receiver configuration snippet and representative PrometheusRule examples, so that the webhook can be connected to lab scenarios.
31. As a developer, I want a local fixture sender script, so that webhook behavior can be exercised without a live Alertmanager.

## Implementation Decisions

- The feature belongs in the root backend and follows the existing FastAPI application factory, environment settings, async SQLAlchemy session factory, persistence models, migrations, router registration, structured logging, and test conventions.
- The incident investigation lab submodule remains the source of scenario fixtures and does not become the application package.
- The webhook contract uses Pydantic v2 models with extra fields tolerated safely so Alertmanager version differences do not crash ingestion.
- The request model covers version, groupKey, truncatedAlerts, status, receiver, groupLabels, commonLabels, commonAnnotations, externalURL, and alerts. Each alert covers status, labels, annotations, startsAt, endsAt, generatorURL, and optional fingerprint.
- Only version `4` is accepted; all other versions produce a clear 422 response.
- The normalized model has source `alertmanager`; optional source fingerprint; status `firing` or `resolved`; severity defaulting to `unknown`; full label and annotation copies; and the original alert object.
- Label extraction is centralized in one pure `normalize_alert(raw_alert, payload_context)` function. Workload selection uses deployment, statefulset, daemonset, and pod-derived identity according to best-effort rules, with generated ReplicaSet/pod hash suffixes stripped.
- Alert-level labels and annotations take precedence over payload context where both provide values; payload context supplies grouped/common values and fallback annotations.
- `0001-01-01T00:00:00Z` is treated as no end time. Receipt time is generated by the server in UTC.
- A `raw_webhooks` persistence record stores an identifier, UTC receipt time, a bounded safe subset of request headers, and the parsed JSON body using PostgreSQL JSONB.
- The request ID is generated or propagated at the HTTP boundary and included in structured logs. Authentication headers, webhook tokens, and full annotation bodies are excluded from info-level logs.
- If `WEBHOOK_TOKEN` is unset, development requests are allowed and a startup warning is emitted. If set, the endpoint requires `Authorization: Bearer <token>` and uses constant-time comparison; missing or incorrect credentials return 401.
- The body limit is approximately 1 MiB and is enforced before normal processing, returning 413 for larger bodies.
- The next-task interface is `async def ingest_alerts(session, alerts: list[NormalizedAlert]) -> list[IngestResult]`. The placeholder returns one action result per accepted alert without deduplication or investigation creation.
- The endpoint returns 202 with `{received, accepted, skipped}` after audit persistence and handoff scheduling/dispatch. Investigation work is not performed inline.
- The implementation does not add LLM calls, queues, Kubernetes calls, deduplication, investigation creation, or remediation.
- Deployment support includes an Alertmanager receiver example, PrometheusRule examples for two existing lab failure scenarios, and a shell fixture sender for local testing.

## Testing Decisions

- Test external HTTP behavior through the existing FastAPI app factory and current TestClient or async HTTP client conventions.
- Parametrize valid endpoint tests over every firing and resolved fixture in the incident investigation lab scenarios.
- Verify 202 responses and received/accepted/skipped counts.
- Verify a multi-alert payload with one malformed alert continues processing and reports the correct accepted/skipped counts.
- Verify wrong versions return 422 with an actionable message.
- Verify oversized bodies return 413.
- Verify missing and incorrect bearer tokens return 401 when `WEBHOOK_TOKEN` is configured, and requests are allowed with a startup warning when it is not configured.
- Verify the raw webhook persistence record contains the parsed body and only the approved header subset.
- Verify the ingestion seam receives normalized alerts and does not perform investigation work.
- Unit-test normalization for pod-hash stripping, missing labels, zero-time end timestamps, resolved status, fallback summary/description, common-label context, and full raw preservation.
- Preserve the repository’s existing style of testing public behavior and persistence metadata without binding tests unnecessarily to private helper implementation details.

## Out of Scope

- Deduplication behavior and alert uniqueness rules.
- Creating, scheduling, or running investigations.
- LLM calls, queues, background worker infrastructure, Kubernetes API calls, Slack notifications, or remediation.
- Replacing the existing authentication system for non-webhook endpoints.
- Supporting Alertmanager payload versions other than v4.
- Building a UI for alerts or investigations.
- Live end-to-end validation against a running Kubernetes cluster or Alertmanager instance.

## Further Notes

The known scenario fixtures are the source examples for this contract. Their static fixtures use the canonical `boutique` namespace and may require adjustment when deployed into another namespace. Alertmanager fields not represented by the explicit contract should remain harmlessly tolerated as extra data, but their semantic meaning should not be inferred until verified against a live Alertmanager payload.
