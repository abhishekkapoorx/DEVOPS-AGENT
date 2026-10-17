# Registered Tool Service

## Problem Statement

The current agent produces tool intent and the CLI directly maps that intent to local subprocesses. This does not support independently registered tools, policy-rich execution, long-running work, or separate tool-service deployment.

## Solution

Create a Tool Service with a typed registry and factory-based adapter construction. The service validates and authorizes every Tool Call, executes the selected adapter, persists lifecycle and audit data, and returns a bounded Tool Result.

## User Stories

1. As an agent developer, I want to call a named registered capability, so that I do not need to know its implementation.
2. As a tool developer, I want to register a new adapter with input and output schemas, so that the agent can use it without changing routing code.
3. As a security operator, I want each tool to declare required scopes and risk classification, so that execution is policy-controlled.
4. As a user, I want destructive tools to require approval, so that the agent cannot silently perform dangerous actions.
5. As an operator, I want timeouts, retries, cancellation, and idempotency, so that external side effects are controlled.
6. As a developer, I want tools to return structured results, so that agents do not parse arbitrary terminal text.
7. As an operator, I want tool calls correlated to runs and traces, so that failures can be diagnosed end to end.
8. As a platform developer, I want remote and local Tool Service adapters, so that the same contract works for managed tools and user-machine tools.

## Implementation Decisions

- Define Tool Definition, Tool Call, Tool Result, Tool Execution Context, and Tool Registry contracts.
- Register tools through a factory that creates request-scoped adapters.
- Require name, version, input schema, output schema, scopes, risk class, timeout, retry policy, and execution mode in each definition.
- Use HTTPS request/response for short tool calls.
- Use durable asynchronous runs plus SSE or polling for long-running calls.
- Require correlation ID, run ID, tool-call ID, idempotency key, authenticated principal, and trace context.
- Enforce policy in the Tool Service even when the Agent Runtime already checked policy.
- Bound stdout, stderr, result size, execution time, concurrency, and retry count.
- Return artifact references for large outputs.
- Keep the internal contract project-owned; add MCP Streamable HTTP as a future interoperability adapter rather than making MCP the domain model.
- For local execution, use an outbound authenticated connector or job-pull model. Do not require the backend to open inbound connections to user machines.

## Testing Decisions

- Test registry discovery, version selection, factory construction, schema rejection, policy rejection, approval, timeout, retry, cancellation, and idempotency.
- Use a fake registered tool for service contract tests.
- Test that secrets and unbounded output are redacted or rejected.
- Test remote and local connector adapters against the same Tool Service contract.
- Test duplicate delivery and retry behavior with side-effecting fake tools.

## Out of Scope

- Implementing every production tool.
- Arbitrary shell execution.
- Letting the model dynamically install Python packages or register tools at runtime.
- Exposing a public unauthenticated tool registry.

## Further Notes

The first vertical slice should be a read-only `git.status` tool, followed by one approval-required tool to validate the safety model.
