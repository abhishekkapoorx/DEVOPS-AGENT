# REST-first pluggable agent architecture

Status: superseded by [Spec 09](../specs/09-client-local-tool-service.md)

This record describes the earlier pluggable runtime design. The current architecture keeps LangGraph on the private backend and moves local command and file execution to the user's CLI helper; see Spec 09.

## Consequences

- Short requests use bounded HTTP request/response calls.
- Long requests use a persisted run plus SSE event delivery.
- CLI credentials and refresh sessions are managed locally by the CLI and never supplied as command-line arguments.
- Conversation identity and LangGraph thread identity are persisted by the backend.
