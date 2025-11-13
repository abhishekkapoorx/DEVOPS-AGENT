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
    """
    context: AgentContext | None = get_context_from_runtime(runtime)
    token = push_runtime_context(context)
    working_directory = get_working_directory(context)
    return token, working_directory


@before_model
def bind_context_before_model(request, handler):
    """
    Middleware that stores runtime context before model invocation.
    """
    token, _ = _bind_context(request.runtime)
    try:
        return handler(request)
    finally:
        pop_runtime_context(token)


@wrap_tool_call
def bind_context_for_tools(request, handler):
    """
    Middleware that ensures tools run inside the working directory context.
    """
    token, working_directory = _bind_context(request.runtime)
    previous_cwd = os.getcwd()
    try:
        if working_directory:
            os.chdir(working_directory)
        return handler(request)
    finally:
        os.chdir(previous_cwd)
        pop_runtime_context(token)


