# Production operations

## Deployment boundaries

- Deploy the FastAPI application and the registered Tool Service as separate processes. Compose `create_app` with PostgreSQL repositories and a configured `AgentRuntime`; compose `create_tool_service_app` with a registered-tool catalog and a `ToolService` backed by `PostgresToolExecutionRepository`.
- Set `DATABASE_URL` only in the backend deployment. The API uses pooled async PostgreSQL connections; migrations are a separate release step.
- Configure HTTPS at the public ingress. The CLI rejects non-loopback HTTP. Do not put access or refresh tokens in command-line arguments or logs.
- Configure the website approval provider, access-token secret, repository allow-list, user-scope resolver, and Tool Service URL through deployment secrets/configuration. Never use a permissive scope resolver in production.

## Release and rollback

1. Back up the database and deploy application code compatible with both the current and target schema.
2. In a migration job, set `DATABASE_URL` and run `python -m alembic upgrade head`.
3. Verify `/health/ready`, authenticate a canary user, create a conversation, stream a run, and execute a read-only registered tool.
4. Roll application code back independently if needed. Prefer a forward-fix migration; `alembic downgrade` is only supported for a rehearsed maintenance rollback after confirming data loss implications.
5. CI validates the revision chain and exercises upgrade/downgrade/upgrade against disposable PostgreSQL. Never run CI rollback commands against a production database.

## Security and retention

- Keep tool definitions allow-listed and versioned. Destructive tools must require a separate trusted approval decision; never derive approval from a request body.
- Tool calls require an idempotency key. Retried adapters must enforce that key at the side-effect boundary. Bound input schemas, timeouts, retries, concurrency and serialized result size.
- Keep correlation IDs and W3C trace context, but do not record authorization headers, raw credentials or unredacted tool payloads. Treat user messages as potentially sensitive.
- Define organization-specific retention periods for conversations, run events, tool audit rows and external artifacts before production launch. Purge through a reviewed scheduled job that preserves audit/legal holds; no automatic retention deletion is enabled by this package yet.
- `/metrics` exports low-cardinality HTTP request counts and durations. The built-in rate limiter is per process; production deployments with multiple workers must inject a shared limiter (for example, a Redis-backed implementation).

## Operational checks

- Alert on readiness failures, run queue age, run/tool failure rates, lease recovery, database pool exhaustion, and elevated API latency.
- Verify logs and traces using correlation IDs from the `X-Correlation-ID` response header.
- Rotate the access-token signing secret as an explicit coordinated operation; existing access tokens become invalid when the verifier secret changes.
- Run dependency and container scanning in CI and review findings before release.
