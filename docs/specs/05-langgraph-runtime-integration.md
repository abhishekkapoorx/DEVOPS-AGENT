# LangGraph runtime integration

## Problem Statement

LangGraph is currently coupled to the server application and does not yet persist agent state through the new conversation and run model or call a separate Tool Service.

## Solution

Implement LangGraph as one Agent Runtime adapter. The adapter maps persisted conversation and run identity to LangGraph thread identity, exposes remote proxy tools, resumes after Tool Results, and persists checkpoints through PostgreSQL.

## User Stories

1. As a user, I want a conversation to retain context across CLI restarts, so that the agent can continue naturally.
2. As an agent runtime operator, I want graph checkpoints persisted, so that process restarts do not lose execution state.
3. As a user, I want an agent run to pause for approval and resume later, so that sensitive work is controlled.
4. As a runtime developer, I want tool results to re-enter the graph as structured messages, so that agents do not depend on transport details.
5. As a platform developer, I want to substitute a fake runtime, so that API tests do not invoke a model.

## Implementation Decisions

- Define an Agent Runtime interface independent of LangGraph.
- Create proxy tools whose implementation submits Tool Calls to the Tool Service.
- Map one conversation to a stable agent thread and one execution attempt to a run.
- Persist checkpoints with a PostgreSQL-backed LangGraph checkpointer.
- Resume the graph from Tool Results or approval decisions.
- Emit normalized run events rather than exposing raw LangGraph events to clients.
- Apply message trimming and summarization through the runtime adapter, not the API routes.
- Keep model configuration and graph construction inside the LangGraph package.

## Testing Decisions

- Use a deterministic fake model and fake Tool Service for runtime tests.
- Test final answers, multiple tool calls, tool failure, approval pause/resume, cancellation, and checkpoint restore.
- Test that malformed graph tool output cannot become a valid Tool Call.
- Test API behavior with a fake Agent Runtime.

## Out of Scope

- Changing the agent’s prompt strategy.
- Adding new specialist agents.
- Exposing LangGraph graph internals through the public API.

## Further Notes

The runtime adapter is the highest seam for replacing LangGraph or running a different agent implementation later.
