# Architecture foundation

## Problem Statement

The current system couples the CLI, WebSocket transport, server agent, tool execution, and in-memory session state. This makes transport changes, persistence, testing, and replacement of the LangGraph implementation unnecessarily expensive.

## Solution

Establish deep module seams between the CLI, FastAPI application, application services, persistence adapters, Agent Runtime, and Tool Service. The public interfaces must use project-owned domain contracts rather than framework-specific types.

## User Stories

1. As a backend developer, I want the API to depend on an Agent Runtime interface, so that LangGraph can be replaced or tested independently.
2. As a CLI developer, I want one HTTP client interface, so that screens do not contain transport, retry, or token logic.
3. As a tool developer, I want tool execution behind a Tool Service interface, so that tools can be registered without modifying the agent or API routes.
4. As a test author, I want in-memory adapters for every external seam, so that behavior can be tested without a database, browser, model, or cloud account.
5. As an operator, I want the application to expose explicit health and readiness states, so that deployment systems can make safe routing decisions.

## Implementation Decisions

- Use REST as the primary application transport.
- Use SSE for resumable progress delivery; WebSockets are optional and not part of the primary contract.
- Define domain contracts for users, sessions, conversations, messages, runs, tool definitions, tool calls, and tool results.
- Keep LangGraph behind an Agent Runtime adapter.
- Keep database access behind repository interfaces.
- Keep Textual widgets unaware of FastAPI, SQL, LangGraph, and tool adapter details.
- Use dependency injection at each seam and avoid service-locator access from domain logic.

## Testing Decisions

- Test each seam through its public interface.
- Use fake Agent Runtime, repository, token store, and Tool Service adapters.
- Add contract tests ensuring each production adapter satisfies the same interface as its fake.
- Add one end-to-end test covering CLI request, API, runtime, persistence, and response.

## Out of Scope

- Replacing LangGraph itself.
- Selecting a cloud deployment platform.
- Building a web frontend beyond the browser handoff required for authentication.

## Further Notes

This is the prerequisite specification for all other work. New code should not extend the existing WebSocket client as the primary architecture.
