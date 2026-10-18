# Glossary

This glossary records the project's domain vocabulary. Add terms here as they become established, with concise definitions and any explicitly avoided synonyms.

| Term | Definition | Avoid / notes |
| --- | --- | --- |
| Agent Runtime | A backend module that accepts a conversation request and executes an agent implementation behind a stable interface. | The API must not depend directly on LangGraph-specific types. |
| Tool Service | A separately deployable execution service that exposes registered tools to an Agent Runtime. | Prefer this over “CLI service”; the service is not limited to shell commands. |
| Tool Definition | The metadata and input/output contract used to register one executable tool. | Must include capability, schema, policy, and execution limits. |
| Tool Call | A validated request from an Agent Runtime to a Tool Service to execute one Tool Definition. | Carries correlation, authorization, idempotency, and trace context. |
| Tool Result | The structured success, failure, or progress outcome returned for a Tool Call. | Never return unbounded raw output by default. |
| Conversation | A user-owned, durable sequence of messages that provides context for agent interactions. | A conversation maps to one stable agent thread; it is not an authentication session. |
| Run | One execution attempt to process a user message, including its status, events, and any Tool Calls. | A retry is a distinct run only when it has a distinct idempotency key. |

