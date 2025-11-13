# Agent Context Management

This module provides utilities to set and manage agent context, particularly the working directory context that agents can use during execution.

## Overview

Following LangChain's context pattern, **context** contains immutable configuration and contextual data that persists throughout the agent's execution. This is different from **state**, which contains mutable data that changes during execution.

## Quick Start

### Setting Working Directory Context

```python
from agent import supervisor
from utils.context import set_working_directory_context

# Set the working directory before invoking
context = set_working_directory_context("/path/to/your/project")

# Invoke the agent with context
result = supervisor.invoke(
    {
        "messages": [
            {"role": "user", "content": "List all files in this directory"}
        ]
    },
    context=context
)
```

### Full Context Example

```python
from utils.context import create_context

context = create_context(
    working_directory="/path/to/project",
    project_root="/path/to/project",
    user_id="user123",
    session_id="session456"
)

result = supervisor.invoke(
    {"messages": [{"role": "user", "content": "Analyze the codebase"}]},
    context=context
)
```

## API Reference

### `AgentContext`

TypedDict schema for agent context:

```python
class AgentContext(TypedDict, total=False):
    working_directory: Optional[str]  # Working directory for file operations
    project_root: Optional[str]       # Root directory of the project
    user_id: Optional[str]            # User identifier
    session_id: Optional[str]        # Session identifier
```

### `create_context()`

Create a full context with all parameters.

**Parameters:**
- `working_directory`: The working directory path (defaults to current directory)
- `project_root`: The project root (defaults to working_directory)
- `user_id`: Optional user identifier
- `session_id`: Optional session identifier

**Returns:** `AgentContext` dictionary

### `set_working_directory_context()`

Convenience function to quickly set just the working directory.

**Parameters:**
- `directory`: The working directory path
- `project_root`: Optional project root (defaults to directory)

**Returns:** `AgentContext` dictionary

### `get_working_directory()`

Get the working directory from context or current directory.

**Parameters:**
- `context`: Optional AgentContext

**Returns:** Working directory path as string

### `get_project_root()`

Get the project root from context or current directory.

**Parameters:**
- `context`: Optional AgentContext

**Returns:** Project root path as string

### `get_context_from_runtime()`

Extract context from LangGraph runtime object (for use in middleware/tools).

**Parameters:**
- `runtime`: LangGraph runtime object

**Returns:** Optional AgentContext

## Using Context in Tools

If you need to access context in your tools or middleware:

```python
from langchain.agents.middleware import before_model
from utils.context import get_context_from_runtime, get_working_directory

@before_model
def use_working_directory(request, handler):
    """Middleware that uses working directory from context."""
    context = get_context_from_runtime(request.runtime)
    working_dir = get_working_directory(context)
    
    # Use working_dir in your logic
    # For example, change to that directory before operations
    import os
    original_cwd = os.getcwd()
    try:
        os.chdir(working_dir)
        # Your logic here
        return handler(request)
    finally:
        os.chdir(original_cwd)
```

## Environment Variable Support

You can also use environment variables:

```python
import os
from utils.context import set_working_directory_context

# Get from environment or use default
working_dir = os.getenv("AGENT_WORKING_DIRECTORY", "/default/path")
context = set_working_directory_context(working_dir)
```

## Examples

See `examples/agent_with_context.py` for complete examples including:
- Basic context usage
- Full context with user/session IDs
- Streaming with context
- Environment variable context

## Notes

- Context is **immutable** during agent execution
- Context is passed when invoking the agent, not when creating it
- Tools and middleware can access context via `request.runtime.context`
- The working directory is validated to exist before use
- All paths are resolved to absolute paths

