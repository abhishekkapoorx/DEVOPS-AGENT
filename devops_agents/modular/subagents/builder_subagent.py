"""
Builder Subagent - Wraps BuilderAgent for DeepAgents integration

Uses the existing BuilderAgent which manages Docker and K8s agents.
"""

from agents.BuilderAgent.agent import agent as builder_agent


def create_builder_subagent():
    """
    Create builder subagent using the existing BuilderAgent.
    
    BuilderAgent is a supervisor that coordinates:
    - DockerAgent: Containerization and Docker tasks
    - K8sAgent: Kubernetes orchestration
    
    Returns:
        Compiled LangGraph graph for builder operations
    """
    return builder_agent


# For backward compatibility
create_docker_subagent = create_builder_subagent

