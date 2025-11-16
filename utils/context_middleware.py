"""
Middleware utilities to bind runtime context to model/tool execution.

These middlewares ensure that tools always operate within the working directory
specified by the agent context (e.g., dummy_projects/harmonia_flask).
"""

from __future__ import annotations

import os
from typing import Any

from langchain.agents.middleware import before_model, wrap_tool_call

from .context import (
    AgentContext,
    get_context_from_runtime,
    get_working_directory,
    push_runtime_context,
    pop_runtime_context,
)


def _bind_context(runtime) -> tuple[Any, str]:
    """
    Bind runtime context and return (token, working_directory).

    token should be passed to pop_runtime_context when finished.
    
    Args:
        runtime: Runtime object (may be None, dict, or object with .context attribute)
    """
    # Handle None runtime
    if runtime is None:
        context = None
    else:
        context: AgentContext | None = get_context_from_runtime(runtime)
    
    token = push_runtime_context(context)
    working_directory = get_working_directory(context)
    return token, working_directory


@before_model
def bind_context_before_model(state, runtime):
    """
    Middleware that stores runtime context before model invocation.
    
    Args:
        state: Agent state
        runtime: Runtime object with context
    """
    token, _ = _bind_context(runtime)
    try:
        return state
    finally:
        pop_runtime_context(token)


@wrap_tool_call
async def bind_context_for_tools(request, handler):
    """
    Middleware that ensures tools run inside the working directory context.
    
    Args:
        request: Tool request object (may be dict or object)
        handler: Handler function to call (can be sync or async)
    """
    # Extract runtime from request
    # request might be a dict or an object with runtime attribute
    if isinstance(request, dict):
        runtime = request.get('runtime')
    elif hasattr(request, 'runtime'):
        runtime = request.runtime
    else:
        # Try to get runtime from handler if it's available
        runtime = getattr(handler, 'runtime', None) if hasattr(handler, 'runtime') else None
    
    token, working_directory = _bind_context(runtime)
    previous_cwd = os.getcwd()
    try:
        if working_directory:
            os.chdir(working_directory)
        # The handler is provided by the framework and will be async when used with async invocation
        # The decorator handles the async/sync distinction
        return await handler(request)
    finally:
        os.chdir(previous_cwd)
        pop_runtime_context(token)


