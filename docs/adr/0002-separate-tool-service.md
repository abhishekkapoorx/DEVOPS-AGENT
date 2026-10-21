# Separate registered-tool execution service

Status: accepted

Agent Runtime tool calls will cross a dedicated Tool Service seam rather than invoking CLI subprocesses directly. The Tool Service will expose a registry of typed Tool Definitions, enforce authorization and execution policy, execute the selected adapter, and return a bounded Tool Result correlated to the original Tool Call. HTTP request/response is the default transport for short tools; asynchronous runs with persisted state and SSE progress are used for long-running tools. MCP Streamable HTTP is a possible future interoperability adapter, but the first implementation should keep the internal Tool Service interface under project control.

## Consequences

- Tool execution is independently deployable and testable.
- The agent can use registered tools that are not shell commands.
- Every tool call requires explicit identity, capability, policy, timeout, idempotency, and trace context.
- The CLI becomes a client or optional local adapter, not the owner of the tool protocol.
