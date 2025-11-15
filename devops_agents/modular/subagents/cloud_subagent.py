"""
Cloud Subagent - Wraps CloudAgent for DeepAgents integration

Uses the existing CloudAgent which manages multi-cloud operations.
"""

from agents.CloudAgent.agent import agent as cloud_agent


def create_cloud_subagent():
    """
    Create cloud subagent using the existing CloudAgent.
    
    CloudAgent is a supervisor that coordinates:
    - AWSAgent: Amazon Web Services operations
    - AzureAgent: Microsoft Azure operations
    - GCPAgent: Google Cloud Platform operations
    
    Supports:
    - Cloud architecture design
    - Resource provisioning
    - Infrastructure planning
    - Cost estimation
    - Security and compliance
    
    Returns:
        Compiled LangGraph graph for cloud operations
    """
    return cloud_agent
