"""
Coder Subagent - Wraps CoderAgent for DeepAgents integration

Uses the existing CoderAgent with deep agent pattern and reflection.
"""

from agents.CoderAgent.agent import agent as coder_agent


def create_coder_subagent():
    """
    Create coder subagent using the existing CoderAgent.
    
    CoderAgent specializes in:
    - File and code management
    - Code quality assurance
    - Multi-step code changes
    - Self-reflection and validation
    - Error recovery
    
    Capabilities:
    - File operations (create, read, update, delete)
    - Code writing and refactoring
    - Code review and validation
    - Quality assurance
    
    Returns:
        Compiled LangGraph graph for code operations
    """
    return coder_agent

