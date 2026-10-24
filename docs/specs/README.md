# Architecture specifications

The current architecture uses a user-installed CLI and local helper for workspace tools, with authentication, orchestration, and run state kept on the backend. Earlier architecture documents are retained as historical records; instructions for a server-hosted Tool Service or WebSocket transport are superseded.

## Delivery streams

1. User package: CLI, local helper, authentication, approval, and workspace-bounded execution.
2. Backend: authentication, durable conversations and runs, LangGraph orchestration, and local-tool request/result endpoints.
3. Cleanup and docs: remove obsolete transports and server-side tool execution; preserve inactive indexing/RAG source and record MCP as future work.
