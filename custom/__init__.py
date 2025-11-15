"""
Custom Deep Agents Implementation

This module contains the custom deep agents implementation with:
- Self-reflection and quality assurance
- Advanced error recovery
- Memory persistence (SQLite/PostgreSQL)
- LangSmith observability integration
- Custom middleware and hooks

Usage:
    from custom import supervisor, invoke_custom_agent
    
    result = invoke_custom_agent(
        message="Create a Dockerfile for my app",
        session_id="my_session"
    )
"""

from .main import supervisor, invoke_custom_agent

__all__ = ["supervisor", "invoke_custom_agent"]


