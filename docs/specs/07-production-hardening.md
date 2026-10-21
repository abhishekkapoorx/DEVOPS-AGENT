# Production hardening

## Problem Statement

The current system lacks a complete operational model for observability, rate limiting, secret handling, retries, cancellation, security testing, and deployment readiness.

## Solution

Add consistent security, reliability, observability, and operational controls across CLI, API, Agent Runtime, persistence, and Tool Service.

## User Stories

1. As an operator, I want one trace to cover CLI, API, runtime, and tool execution, so that incidents can be diagnosed.
2. As an operator, I want metrics for latency, failures, retries, queue depth, and active runs, so that capacity issues are visible.
3. As a security operator, I want secrets redacted from logs, events, traces, and persisted results.
4. As an operator, I want rate limits and concurrency limits, so that abuse and accidental overload are contained.
5. As a user, I want cancellation to stop work where supported, so that I can control long-running operations.
6. As a release engineer, I want migrations, readiness checks, and rollback guidance, so that deployments are repeatable.
7. As a compliance operator, I want durable audit records for tool calls and approvals, so that sensitive actions are reviewable.

## Implementation Decisions

- Propagate trace context across all remote calls and persist correlation identifiers.
- Emit structured logs with stable event names and no secret-bearing payloads.
- Add request, run, tool, and database metrics with low-cardinality labels.
- Enforce authentication, authorization, ownership, rate limits, timeouts, and payload limits at the API.
- Enforce an independent policy check at the Tool Service.
- Use exponential backoff only for retryable failures and require idempotency for retried side effects.
- Add explicit cancellation and expiry states to runs and tool calls.
- Define retention policies for messages, events, audit data, and artifacts.
- Add dependency and container vulnerability scanning to CI.

## Testing Decisions

- Add security tests for token misuse, ownership bypass, replay, injection, and secret leakage.
- Add failure-injection tests for database, model, Tool Service, and external API outages.
- Add load tests for short requests, SSE reconnects, and concurrent tool calls.
- Add migration upgrade and rollback checks.
- Verify trace continuity and redaction in integration tests.

## Out of Scope

- Multi-region active-active deployment.
- Formal compliance certification.
- Provider-specific disaster recovery implementation.

## Further Notes

Operational controls should be built alongside each vertical slice, not postponed until the end of the project.
