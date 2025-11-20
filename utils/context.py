"""
Context management utilities for agent runtime configuration.

This module provides utilities to set and manage agent context, particularly
the working directory context that agents and tools can use during execution.
"""

from typing import Optional, TypedDict, Any
from pathlib import Path
import os
from contextvars import ContextVar


class AgentContext(TypedDict, total=False):
    """
    Runtime context schema for agents.
    
    Context contains immutable configuration and contextual data that persists
    throughout the agent's execution. This follows LangChain's context pattern.
    
    Fields:
    - working_directory: Optional[str] - The working directory path for file operations
    - project_root: Optional[str] - The root directory of the project being worked on
    - user_id: Optional[str] - User identifier for multi-user scenarios
    - session_id: Optional[str] - Session identifier for tracking
    """
    working_directory: Optional[str]
    project_root: Optional[str]
    user_id: Optional[str]
    session_id: Optional[str]


def create_context(
    working_directory: Optional[str] = None,
    project_root: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> AgentContext:
    """
    Create an agent context with the specified parameters.
    
    Parameters
    ----------
    working_directory
        The working directory path for file operations. If None, uses current directory.
    project_root
        The root directory of the project. If None, uses working_directory.
    user_id
        Optional user identifier for multi-user scenarios.
    session_id
        Optional session identifier for tracking.
    
    Returns
    -------
    AgentContext
        A context dictionary ready to pass to agent.invoke()
    
    Examples
    --------
    >>> context = create_context(working_directory="/path/to/project")
    >>> result = agent.invoke({"messages": [...]}, context=context)
    """
    # Resolve and validate working directory
    if working_directory:
        working_dir = Path(working_directory).resolve()
        if not working_dir.exists():
            raise ValueError(f"Working directory does not exist: {working_directory}")
        if not working_dir.is_dir():
            raise ValueError(f"Working directory is not a directory: {working_directory}")
        working_directory = str(working_dir)
    else:
        working_directory = str(Path.cwd().resolve())
    
    # Set project_root to working_directory if not specified
    if project_root:
        project_root_path = Path(project_root).resolve()
        if not project_root_path.exists():
            raise ValueError(f"Project root does not exist: {project_root}")
        project_root = str(project_root_path)
    else:
        project_root = working_directory
    
    context: AgentContext = {
        "working_directory": working_directory,
        "project_root": project_root,
    }
    
    if user_id:
        context["user_id"] = user_id
    if session_id:
        context["session_id"] = session_id
    
    return context


def get_working_directory(context: Optional[AgentContext] = None) -> str:
    """
    Get the working directory from context or current directory.
    
    Parameters
    ----------
    context
        Optional agent context. If None, returns current directory.
    
    Returns
    -------
    str
        The working directory path
    """
    if context and "working_directory" in context:
        return context["working_directory"]
    return str(Path.cwd().resolve())


def get_project_root(context: Optional[AgentContext] = None) -> str:
    """
    Get the project root from context or current directory.
    
    Parameters
    ----------
    context
        Optional agent context. If None, returns current directory.
    
    Returns
    -------
    str
        The project root path
    """
    if context and "project_root" in context:
        return context["project_root"]
    return str(Path.cwd().resolve())


def set_working_directory_context(
    directory: str,
    project_root: Optional[str] = None
) -> AgentContext:
    """
    Convenience function to create context with just a working directory.
    
    Parameters
    ----------
    directory
        The working directory path
    project_root
        Optional project root. If None, uses directory.
    
    Returns
    -------
    AgentContext
        Context ready to use with agent.invoke()
    
    Examples
    --------
    >>> from utils.context import set_working_directory_context
    >>> context = set_working_directory_context("/path/to/project")
    >>> result = supervisor.invoke({"messages": [...]}, context=context)
    """
    return create_context(
        working_directory=directory,
        project_root=project_root
    )


def get_context_from_runtime(runtime) -> Optional[AgentContext]:
    """
    Extract context from LangGraph runtime object or config.
    
    This helper function allows tools and middleware to access the context
    that was passed when invoking the agent.
    
    Parameters
    ----------
    runtime
        The runtime object from LangGraph (available in middleware hooks)
        May also be a dict with 'config' key containing configurable context
    
    Returns
    -------
    Optional[AgentContext]
        The context if available, None otherwise
    
    Examples
    --------
    >>> from langchain.agents.middleware import before_model
    >>> 
    >>> @before_model
    >>> def use_context(request, handler):
    >>>     context = get_context_from_runtime(request.runtime)
    >>>     if context:
    >>>         working_dir = context.get("working_directory")
    >>>         # Use working_dir in your logic
    >>>     return handler(request)
    """
    # Try runtime.context attribute first
    if hasattr(runtime, "context"):
        return runtime.context
    
    # Try config.configurable.context (for deepagents/LangGraph)
    if isinstance(runtime, dict):
        config = runtime.get("config", {})
        if isinstance(config, dict):
            configurable = config.get("configurable", {})
            if isinstance(configurable, dict):
                context = configurable.get("context")
                if context:
                    return context
    
    # Try runtime.config.configurable.context
    if hasattr(runtime, "config"):
        config = runtime.config
        if isinstance(config, dict):
            configurable = config.get("configurable", {})
            if isinstance(configurable, dict):
                context = configurable.get("context")
                if context:
                    return context
    
    return None


# ---------------------------------------------------------------------------
# Runtime context (ContextVar) helpers
# ---------------------------------------------------------------------------

_CURRENT_CONTEXT: ContextVar[Optional[AgentContext]] = ContextVar(
    "current_agent_context",
    default=None,
)


def push_runtime_context(context: Optional[AgentContext]) -> Any:
    """
    Push context onto the context variable stack.

    Returns a token that must be used with ``pop_runtime_context``.
    """
    return _CURRENT_CONTEXT.set(context)


def pop_runtime_context(token: Any) -> None:
    """Restore previous context using the token returned by push_runtime_context."""
    if token is not None:
        _CURRENT_CONTEXT.reset(token)


def get_current_context() -> Optional[AgentContext]:
    """Return the context associated with the current execution context."""
    return _CURRENT_CONTEXT.get()


# ---------------------------------------------------------------------------
# Helpers for working with the dummy_projects directory
# ---------------------------------------------------------------------------

def get_dummy_projects_path() -> Path:
    """
    Get the path to the dummy_projects directory.

    This is a convenience function to easily access test projects.

    Returns
    -------
    Path
        Path to dummy_projects directory
    """
    # utils/context.py -> utils -> project root
    project_root = Path(__file__).resolve().parent.parent
    dummy_projects = project_root / "dummy_projects"

    if not dummy_projects.exists():
        raise ValueError(
            f"dummy_projects directory not found at: {dummy_projects}"
        )

    return dummy_projects

def get_dummy_projects_path() -> Path:
    """
    Get the path to the dummy_projects directory.
    
    This is a convenience function to easily access test projects.
    
    Returns
    -------
    Path
        Path to dummy_projects directory
    
    Examples
    --------
    >>> from utils.context import get_dummy_projects_path, set_working_directory_context
    >>> 
    >>> dummy_path = get_dummy_projects_path()
    >>> harmonia_path = dummy_path / "harmonia_flask"
    >>> context = set_working_directory_context(str(harmonia_path))
    """
    # Get the project root (assuming this file is in utils/)
    project_root = Path(__file__).parent.parent
    dummy_projects = project_root / "dummy_projects"
    
    if not dummy_projects.exists():
        raise ValueError(f"dummy_projects directory not found at: {dummy_projects}")
    
    return dummy_projects
