"""
Enhanced State Schema for Deep Agents with Reflection Support

This module provides comprehensive state schemas for deep agents that support:
- Reflection and self-critique mechanisms
- Enhanced memory and context management
- Error tracking and recovery
- Performance metrics and observability
- Multi-step reasoning with intermediate results
"""

from typing import Optional, List, Dict, Any, Literal
from typing_extensions import Annotated
from langgraph.prebuilt.chat_agent_executor import AgentState
from langgraph.graph.message import add_messages
from datetime import datetime


class ReflectionState(AgentState):
    """
    Enhanced state schema for deep agents with reflection capabilities.
    
    This extends AgentState and adds deep agent-specific fields for:
    - Self-reflection and critique
    - Performance tracking
    - Error handling and recovery
    - Multi-step reasoning
    - Observability metrics
    """
    
    # Planning and Strategy
    plan: Optional[str]  # Current execution plan
    plan_history: Annotated[List[str], lambda x, y: x + [y] if y else x]  # Plan evolution history
    plan_version: int  # Current plan version
    
    # Reflection and Self-Critique
    reflections: Annotated[List[Dict[str, Any]], lambda x, y: x + [y] if y else x]  # Self-critiques
    critique: Optional[str]  # Latest critique of agent's work
    confidence_score: Optional[float]  # Confidence in current approach (0-1)
    should_revise: bool  # Whether agent should revise its approach
    revision_count: int  # Number of times agent has revised
    max_revisions: int  # Maximum revisions allowed
    
    # Multi-step Reasoning
    current_step: Optional[str]  # Current step being executed
    completed_steps: Annotated[List[str], lambda x, y: x + [y] if y else x]  # Completed steps
    pending_steps: List[str]  # Remaining steps
    intermediate_results: Dict[str, Any]  # Results from each step
    
    # Error Handling and Recovery
    errors: Annotated[List[Dict[str, Any]], lambda x, y: x + [y] if y else x]  # Error log
    last_error: Optional[str]  # Most recent error
    retry_count: int  # Number of retries
    max_retries: int  # Maximum retries allowed
    fallback_strategy: Optional[str]  # Fallback approach if primary fails
    
    # Context and Memory
    rag_context: Optional[str]  # Retrieved context from RAG
    working_memory: Dict[str, Any]  # Short-term working memory
    long_term_context: Optional[str]  # Persistent context across sessions
    
    # Observability and Metrics
    execution_start_time: Optional[str]  # When execution started
    step_timings: Dict[str, float]  # Time taken for each step
    tool_calls: Annotated[List[Dict[str, Any]], lambda x, y: x + [y] if y else x]  # Tool usage log
    tokens_used: int  # Total tokens consumed
    
    # Agent Metadata
    agent_name: Optional[str]  # Name of the agent
    agent_version: Optional[str]  # Version of agent logic
    session_id: Optional[str]  # Session identifier


class DockerAgentState(ReflectionState):
    """
    Specialized state for Docker Agent with containerization-specific fields.
    """
    analysis_result: Optional[str]  # Codebase analysis results
    dockerfile_content: Optional[str]  # Generated Dockerfile
    compose_content: Optional[str]  # Generated docker-compose.yml
    user_requirements: Optional[str]  # User's specific requirements
    output_directory: Optional[str]  # Where to write files
    project_root: Optional[str]  # Project root directory
    optimization_suggestions: List[str]  # Optimization recommendations


class K8sAgentState(ReflectionState):
    """
    Specialized state for Kubernetes Agent with orchestration-specific fields.
    """
    app_requirements: Optional[str]  # Application requirements analysis
    manifests_content: Optional[str]  # Generated K8s manifests
    helm_chart_content: Optional[str]  # Generated Helm chart
    user_requirements: Optional[str]  # User's specific requirements
    output_directory: Optional[str]  # Where to write files
    cluster_recommendations: List[str]  # K8s best practices recommendations


class CloudAgentState(ReflectionState):
    """
    Specialized state for Cloud Agents (AWS, Azure, GCP) with cloud-specific fields.
    """
    cloud_provider: Optional[Literal["aws", "azure", "gcp"]]  # Target cloud
    infrastructure_plan: Optional[str]  # Infrastructure as code plan
    resources_created: List[str]  # List of created cloud resources
    cost_estimate: Optional[float]  # Estimated monthly cost
    security_findings: List[str]  # Security audit findings
    compliance_status: Dict[str, bool]  # Compliance checks


class CoderAgentState(ReflectionState):
    """
    Specialized state for Coder Agent with file management fields.
    """
    files_modified: Annotated[List[str], lambda x, y: x + [y] if y else x]  # Modified files
    files_created: Annotated[List[str], lambda x, y: x + [y] if y else x]  # Created files
    files_deleted: Annotated[List[str], lambda x, y: x + [y] if y else x]  # Deleted files
    code_quality_score: Optional[float]  # Code quality metric
    test_coverage: Optional[float]  # Test coverage percentage


class ThinkerAgentState(ReflectionState):
    """
    Specialized state for Thinker Agent - strategic planning and reflection.
    """
    strategic_analysis: Optional[str]  # High-level strategic analysis
    risk_assessment: Optional[str]  # Risk analysis
    alternative_approaches: List[str]  # Alternative solution approaches
    decision_rationale: Optional[str]  # Reasoning behind decisions
    success_criteria: List[str]  # How to measure success


class WatcherAgentState(ReflectionState):
    """
    Specialized state for Watcher Agent - monitoring and observability.
    """
    system_health: Optional[str]  # Overall system health status
    performance_metrics: Dict[str, Any]  # Performance metrics
    alerts: Annotated[List[Dict[str, Any]], lambda x, y: x + [y] if y else x]  # System alerts
    anomalies_detected: List[str]  # Detected anomalies
    recommendations: List[str]  # Performance recommendations


# Helper function to create initial reflection state
def create_initial_reflection_state(**kwargs) -> Dict[str, Any]:
    """
    Create an initial reflection state with sensible defaults.
    
    Args:
        **kwargs: Override any default values
        
    Returns:
        Dictionary with initialized reflection state fields
    """
    defaults = {
        "messages": [],
        "plan": None,
        "plan_history": [],
        "plan_version": 0,
        "reflections": [],
        "critique": None,
        "confidence_score": None,
        "should_revise": False,
        "revision_count": 0,
        "max_revisions": 3,
        "current_step": None,
        "completed_steps": [],
        "pending_steps": [],
        "intermediate_results": {},
        "errors": [],
        "last_error": None,
        "retry_count": 0,
        "max_retries": 3,
        "fallback_strategy": None,
        "rag_context": None,
        "working_memory": {},
        "long_term_context": None,
        "execution_start_time": datetime.utcnow().isoformat(),
        "step_timings": {},
        "tool_calls": [],
        "tokens_used": 0,
        "agent_name": None,
        "agent_version": "1.0.0",
        "session_id": None,
    }
    
    defaults.update(kwargs)
    return defaults

