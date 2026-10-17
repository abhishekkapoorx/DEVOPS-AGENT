# REST-first pluggable agent architecture

Status: accepted

The system will use a REST-first FastAPI backend, browser-assisted device authentication for the CLI, a Textual terminal UI, PostgreSQL-backed conversations and agent persistence, and SSE for long-running progress. The LangGraph implementation will be isolated behind a pluggable Agent Runtime interface so the API and persistence layers do not depend on LangGraph-specific implementation details. WebSockets are not the primary application contract and are deferred unless a later requirement needs bidirectional interaction.

## Consequences

- Short requests use bounded HTTP request/response calls.
- Long requests use a persisted run plus SSE event delivery.
- CLI credentials and refresh sessions are managed locally by the CLI and never supplied as command-line arguments.
- Conversation identity and LangGraph thread identity are persisted by the backend.
