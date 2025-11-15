"""
Modular DeepAgents Implementation - CompiledSubAgent Pattern (RECOMMENDED)

This is the gold-standard implementation using:
- CompiledSubAgent for all subagents
- Modular design with separate files
- Context quarantine
- All best practices from deepagents documentation

Usage:
    from devops_agents.modular import invoke_modular_agent
    
    result = invoke_modular_agent(
        message="Create a Dockerfile for my app",
        thread_id="my_task"
    )
"""

from .main import create_modular_agent, invoke_modular_agent

__all__ = ["create_modular_agent", "invoke_modular_agent"]

