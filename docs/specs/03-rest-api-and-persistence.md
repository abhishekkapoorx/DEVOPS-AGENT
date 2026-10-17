# REST API and persistence

## Problem Statement

The current backend uses a WebSocket conversation loop with in-memory session history. It cannot reliably resume conversations or agent runs after process restarts.

## Solution

Build modular FastAPI routes backed by application services and PostgreSQL repositories. Persist users, sessions, conversations, messages, runs, events, tool calls, and audit records. Use a pooled Neon connection for application traffic and migrations as a separate operational concern.

## User Stories

1. As a user, I want to create and list my conversations, so that I can return to prior work.
2. As a user, I want to submit a message and receive a stable message identifier, so that retries do not duplicate it.
3. As a user, I want to reconnect to an active run, so that terminal interruptions do not lose progress.
4. As a user, I want conversation history to survive backend restarts, so that my work is durable.
5. As an operator, I want readiness to include database connectivity, so that unhealthy instances are removed from service.
6. As a security operator, I want every resource query scoped by user and tenant ownership, so that conversations cannot leak across accounts.

## Implementation Decisions

- Version routes under `/v1`.
- Separate route handlers, application services, repositories, schemas, and infrastructure adapters.
- Use idempotency keys for message creation and run creation.
- Persist ordered messages and append-only run events.
- Model run states explicitly: pending, running, waiting_for_approval, completed, failed, cancelled, expired.
- Store large tool outputs as artifact references rather than unbounded database fields or API responses.
- Store a stable conversation-to-agent-thread mapping for LangGraph persistence.
- Use database migrations and a controlled startup migration policy.

## Testing Decisions

- Use API contract tests for status codes, response schemas, ownership, and idempotency.
- Use repository tests against disposable PostgreSQL where possible.
- Use transaction rollback fixtures for service tests.
- Test reconnect and event replay from a stored event sequence.
- Test database outage behavior separately from application validation errors.

## Out of Scope

- Billing, quotas, and multi-region replication.
- Full-text search over conversations.
- Object storage provider selection.

## Further Notes

Postgres is the source of truth for user-visible state. In-memory state may be used only as a cache or short-lived process coordination state.
