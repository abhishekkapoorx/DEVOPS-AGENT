# Planning Node Module

A standardized, reusable planning system for LangGraph workflows.

## Quick Start

```python
from utils.planning import create_planning_hook, PlanState
from utils.plan_state import PlanningStateMixin
from llms import DEFAULT_MODEL
from langgraph_supervisor import create_supervisor

# Simple usage with defaults
planning_hook = create_planning_hook(model=DEFAULT_MODEL)

# Use in your graph
supervisor = create_supervisor(
    ...,
    state_schema=PlanState,
    pre_model_hook=planning_hook
)
```

## Advanced Usage

### Custom Configuration

```python
from utils.planning import PlanningNode

planning_hook = PlanningNode(
    model=DEFAULT_MODEL,
    min_messages_for_update=10,  # Wait for more messages before checking updates
    max_plan_versions=5,          # Allow more plan revisions
    recent_context_window=10,     # Consider more messages for context
)
```

### Custom Prompts

```python
planning_hook = PlanningNode(
    model=DEFAULT_MODEL,
    plan_generation_prompt="Create a detailed DevOps plan...",
    update_decision_prompt="Should we update the plan? Consider...",
    plan_update_prompt="Update the plan based on...",
)
```

### Custom State Schema

```python
from typing_extensions import TypedDict
from langgraph.prebuilt.chat_agent_executor import AgentState
from utils.plan_state import PlanningStateMixin

class MyCustomState(AgentState, PlanningStateMixin):
    custom_field: str
    # ... other fields
```

### Custom User Message Extractor

```python
def extract_user_message(messages):
    # Custom logic to find user message
    for msg in reversed(messages):
        if hasattr(msg, 'role') and msg.role == 'user':
            return msg.content
    return None

planning_hook = PlanningNode(
    model=DEFAULT_MODEL,
    user_message_extractor=extract_user_message
)
```

## Features

- ✅ **LLM-powered planning**: Uses LLM to generate intelligent, context-aware plans
- ✅ **Automatic updates**: Dynamically revises plans when circumstances change
- ✅ **Configurable**: Customize prompts, thresholds, and behavior
- ✅ **Reusable**: Works with any LangGraph workflow
- ✅ **State management**: Maintains plan history and versioning
- ✅ **Error handling**: Graceful fallbacks if LLM calls fail

## Integration Examples

### With create_supervisor

```python
from langgraph_supervisor import create_supervisor
from utils.planning import create_planning_hook, PlanState

planning_hook = create_planning_hook(model=DEFAULT_MODEL)

supervisor = create_supervisor(
    agents=[agent1, agent2],
    model=DEFAULT_MODEL,
    state_schema=PlanState,
    pre_model_hook=planning_hook,
)
```

### With custom StateGraph

```python
from langgraph.graph import StateGraph, START
from utils.plan_state import PlanningStateMixin
from utils.planning import create_planning_hook

class MyState(AgentState, PlanningStateMixin):
    pass

planning_hook = create_planning_hook(model=DEFAULT_MODEL)

graph = StateGraph(MyState)
graph.add_node("planning", planning_hook)
graph.add_node("agent", agent_node)
graph.add_edge(START, "planning")
graph.add_edge("planning", "agent")
```

## API Reference

### `PlanningNode`

Main class for planning functionality.

**Parameters:**
- `model: LanguageModelLike` - LLM model to use
- `plan_generation_prompt: Optional[str]` - Prompt for initial plan generation
- `update_decision_prompt: Optional[str]` - Prompt for update decision
- `plan_update_prompt: Optional[str]` - Prompt for plan updates
- `min_messages_for_update: int = 5` - Minimum messages before checking updates
- `max_plan_versions: int = 3` - Maximum number of plan versions
- `recent_context_window: int = 5` - Number of recent messages for context
- `user_message_extractor: Optional[Callable]` - Custom message extraction function

### `create_planning_hook(model, **kwargs)`

Convenience function for quick setup.

### `PlanningStateMixin`

TypedDict mixin that adds planning fields to any state schema.

**Fields:**
- `plan: Optional[str]` - Current plan
- `plan_history: List[str]` - History of plan changes
- `plan_version: int` - Current plan version number

### `PlanState`

Complete state schema combining `AgentState` and `PlanningStateMixin`.

