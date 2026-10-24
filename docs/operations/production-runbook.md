# Production operations

## Deployment boundaries

- Deploy one backend with Postgres. Users install the CLI/helper package separately; the backend never mounts a user workspace.
- Run Alembic migrations as a release step and configure the public HTTPS URL, auth settings, token secret, model provider, and provider credentials on the server.
- Keep access and refresh tokens out of process arguments and logs. The CLI stores refresh credentials in the OS credential store when available.
- Tool requests are queued in the running API process and delivered over authenticated SSE. Run one API process until the request queue is moved to shared durable storage.
- Only one local helper can connect for an account at a time so the backend cannot route work to the wrong workspace.

## Release checks

1. Back up the database and apply migrations.
2. Check `/health/ready`, sign in a canary user, start a conversation, and complete a locally executed tool request.
3. Verify `DEVOPS_AGENT_ENABLE_MCP_AGENTS` is false. If true, startup must fail clearly.
4. Confirm the server starts without MCP dependencies and does not import indexing/RAG modules.

## Security and retention

- Local shell commands always require user approval. File writes and deletes require approval; local paths must stay inside the helper's launch directory.
- Keep HTTPS at the public ingress. Do not log authorization headers, raw credentials, or unredacted tool results.
- Define retention for conversations and run events before production use. Monitor run queue age, helper timeouts, API errors, and database health.
- The in-process tool request queue is not shared across multiple API workers; use a single API worker in this release.
