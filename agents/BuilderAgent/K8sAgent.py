"""
Kubernetes Agent - Deep Agent Pattern with Reflection

This deep agent specializes in Kubernetes orchestration with:
- Intelligent requirements analysis
- Production-ready manifest generation
- Helm chart creation
- K8s best practices enforcement
- Self-reflection and quality assurance
"""

from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, HumanMessage
from typing import Dict, Any
from loguru import logger

from llms import DEFAULT_MODEL
from tools.AgentTools.k8s_tools import (
    generate_k8s_manifests,
    generate_helm_chart,
    generate_k8s_service,
    analyze_k8s_requirements,
    generate_k8s_manifests_with_llm,
    generate_helm_chart_with_llm,
    review_k8s_configuration,
)
from langchain_community.agent_toolkits.file_management.toolkit import FileManagementToolkit
from utils.deep_agent_state import K8sAgentState, create_initial_reflection_state
from utils.reflection import ReflectionNode, create_error_recovery_node
from utils.context_middleware import (
    bind_context_before_model,
    bind_context_for_tools,
)


K8S_AGENT_PROMPT = """# Kubernetes Agent - Orchestration Expert

## Role and Purpose
You are a Kubernetes orchestration expert specialized in creating production-ready 
Kubernetes deployments with security, scalability, and reliability best practices.

## Core Capabilities
1. **Requirements Analysis**: Understand application deployment needs
2. **Manifest Generation**: Create comprehensive K8s manifests (Deployments, Services, ConfigMaps, etc.)
3. **Helm Charts**: Generate production-ready Helm charts
4. **Security**: Implement RBAC, NetworkPolicies, PodSecurityPolicies
5. **Scalability**: Configure HPA, resource limits, and auto-scaling
6. **Observability**: Set up monitoring, logging, and health checks

## Workflow - Plan-Deploy-Monitor-Optimize (PDMO)

### 1. Plan
- Analyze application requirements
- Determine resource needs
- Plan scaling strategy
- Design network topology
- Consider security requirements

### 2. Deploy
- Generate Deployment manifests
- Create Service definitions
- Set up ConfigMaps and Secrets
- Configure Ingress rules
- Implement health checks

### 3. Monitor
- Add Prometheus metrics
- Configure logging
- Set up alerts
- Define dashboards

### 4. Optimize
- Configure resource limits
- Implement HPA
- Optimize pod placement
- Tune performance

## Kubernetes Best Practices (Always Follow)

### Security
- Use least-privilege RBAC
- Implement NetworkPolicies
- Run as non-root users
- Use PodSecurityPolicies/PodSecurityStandards
- Manage secrets securely
- Enable audit logging
- Scan images for vulnerabilities

### Reliability
- Set appropriate resource requests/limits
- Configure liveness and readiness probes
- Implement graceful shutdown
- Use PodDisruptionBudgets
- Plan for rolling updates
- Set up backups

### Scalability
- Configure HorizontalPodAutoscaler
- Use appropriate replica counts
- Plan node sizing
- Implement caching strategies
- Use StatefulSets for stateful apps

### Observability
- Add Prometheus annotations
- Configure structured logging
- Set up distributed tracing
- Create monitoring dashboards
- Define alerting rules

### Maintainability
- Use descriptive labels and annotations
- Organize with namespaces
- Version your deployments
- Document configurations
- Use GitOps practices

## Tools Available
- `analyze_k8s_requirements`: Analyze deployment requirements
- `generate_k8s_manifests_with_llm`: Create intelligent K8s manifests
- `generate_helm_chart_with_llm`: Create comprehensive Helm charts
- `review_k8s_configuration`: Review and optimize configurations
- File management tools for reading/writing files

## Process
1. **Analyze requirements** using `analyze_k8s_requirements`
2. **Generate manifests** using `generate_k8s_manifests_with_llm`
3. **Create Helm chart** if needed using `generate_helm_chart_with_llm`
4. **Review configurations** using `review_k8s_configuration`
5. **Reflect on quality** and revise if confidence is low
6. **Provide deployment instructions**

## Output Format
Provide:
- Requirements analysis summary
- Generated Kubernetes manifests
- Helm chart (if requested)
- Security considerations
- Scaling recommendations
- Deployment instructions
- Monitoring setup guide

Begin by analyzing requirements and then generating Kubernetes configurations."""


def create_k8s_agent() -> StateGraph:
    """
    Create Kubernetes Agent with deep agent pattern and reflection.
    
    Returns:
        Compiled LangGraph with K8s agent nodes
    """
    
    # Get working directory for file tools
    import os
    root_dir = os.environ.get("PROJECT_ROOT", ".")
    file_tools = FileManagementToolkit(root_dir=root_dir).get_tools()
    
    # Combine all tools
    k8s_tools = [
        generate_k8s_manifests,
        generate_helm_chart,
        generate_k8s_service,
        analyze_k8s_requirements,
        generate_k8s_manifests_with_llm,
        generate_helm_chart_with_llm,
        review_k8s_configuration,
    ]
    all_tools = file_tools + k8s_tools
    
    # Create the agent with tools
    agent = create_agent(
        model=DEFAULT_MODEL,
        tools=all_tools,
        name="k8s_agent",
        system_prompt=K8S_AGENT_PROMPT,
        middleware=[bind_context_before_model, bind_context_for_tools],
    )
    
    # Create reflection node
    reflection_node = ReflectionNode(
        model=DEFAULT_MODEL,
        min_confidence_threshold=0.75,
        max_reflection_iterations=3,
    )
    
    # Create error recovery node
    error_recovery = create_error_recovery_node(model=DEFAULT_MODEL, max_retries=3)
    
    # Define main agent node
    async def k8s_node(state: K8sAgentState) -> Dict[str, Any]:
        """Main Kubernetes agent execution node."""
        try:
            logger.info("K8s Agent: Starting orchestration workflow")
            
            # Update step tracking
            current_step = state.get("current_step", "initialization")
            completed_steps = state.get("completed_steps", [])
            
            # Invoke agent
            result = await agent.ainvoke(state)
            
            # Track successful execution
            completed_steps = list(completed_steps) + [current_step]
            
            return {
                **result,
                "completed_steps": completed_steps,
                "current_step": "k8s_generation_complete",
            }
            
        except Exception as e:
            logger.error(f"K8s Agent error: {e}")
            errors = state.get("errors", [])
            return {
                **state,
                "last_error": str(e),
                "errors": errors + [{"error": str(e), "node": "k8s_agent", "step": current_step}],
            }
    
    # Define reflection node wrapper
    async def reflect_node(state: K8sAgentState) -> Dict[str, Any]:
        """Reflection node for quality assurance."""
        logger.info("K8s Agent: Performing quality reflection")
        return reflection_node.reflect(state)
    
    # Define revision node
    async def revise_node(state: K8sAgentState) -> Dict[str, Any]:
        """Revision node to improve K8s configurations."""
        try:
            critique = state.get("critique", "")
            
            # Create revision prompt
            revision_message = f"""Based on this quality review, please revise the Kubernetes configurations:

Critique: {critique}

Please improve the manifests and/or Helm chart to address these concerns."""
            
            messages = state.get("messages", [])
            messages = messages + [HumanMessage(content=revision_message)]
            
            # Re-invoke agent for revision
            result = await agent.ainvoke({**state, "messages": messages})
            
            return {
                **result,
                "should_revise": False,  # Reset after revision
                "current_step": "revision_complete",
            }
            
        except Exception as e:
            logger.error(f"Revision error: {e}")
            return state
    
    # Define error recovery node wrapper
    async def recover_node(state: K8sAgentState) -> Dict[str, Any]:
        """Error recovery node."""
        logger.info("K8s Agent: Attempting error recovery")
        return error_recovery(state)
    
    # Routing functions
    def route_after_execution(state: K8sAgentState) -> str:
        """Route after main execution."""
        last_error = state.get("last_error")
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)
        
        # If there's an error and we haven't exceeded retries, try recovery
        if last_error and retry_count < max_retries:
            return "recover"
        
        # Otherwise, proceed to reflection
        return "reflect"
    
    def route_after_reflection(state: K8sAgentState) -> str:
        """Route after reflection."""
        should_revise = state.get("should_revise", False)
        revision_count = state.get("revision_count", 0)
        max_revisions = state.get("max_revisions", 3)
        
        # If we should revise and haven't exceeded limit, go to revision
        if should_revise and revision_count < max_revisions:
            return "revise"
        
        return "end"
    
    # Build the graph
    graph = StateGraph(K8sAgentState)
    
    # Add nodes
    graph.add_node("k8s_agent", k8s_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("revise", revise_node)
    graph.add_node("recover", recover_node)
    
    # Add edges
    graph.add_edge(START, "k8s_agent")
    graph.add_conditional_edges(
        "k8s_agent",
        route_after_execution,
        {
            "recover": "recover",
            "reflect": "reflect",
        }
    )
    graph.add_edge("recover", "k8s_agent")  # Retry after recovery
    graph.add_conditional_edges(
        "reflect",
        route_after_reflection,
        {
            "revise": "revise",
            "end": END,
        }
    )
    graph.add_edge("revise", "reflect")  # Re-reflect after revision
    
    return graph


# Create and compile the agent
agent = create_k8s_agent().compile(name="k8s_agent").with_config({"recursion_limit": 150})
