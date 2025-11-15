"""
Docker Agent - Deep Agent Pattern with Reflection

This deep agent specializes in containerization with:
- Intelligent codebase analysis
- Production-ready Dockerfile generation
- Docker Compose orchestration
- Security and optimization best practices
- Self-reflection and quality assurance
"""

from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, HumanMessage
from typing import Dict, Any
from loguru import logger

from llms import DEFAULT_MODEL
from tools.AgentTools.docker_tools import (
    analyze_codebase,
    generate_dockerfile,
    generate_docker_compose,
    generate_dockerfile_with_llm,
    generate_docker_compose_with_llm,
    review_docker_configuration,
)
from langchain_community.agent_toolkits.file_management.toolkit import FileManagementToolkit
from utils.deep_agent_state import DockerAgentState, create_initial_reflection_state
from utils.reflection import ReflectionNode, create_error_recovery_node
from utils.context_middleware import (
    bind_context_before_model,
    bind_context_for_tools,
)


DOCKER_AGENT_PROMPT = """# Docker Agent - Containerization Expert

## Role and Purpose
You are a Docker containerization expert specialized in creating production-ready 
containerized applications with security and optimization best practices.

## Core Capabilities
1. **Codebase Analysis**: Detect languages, frameworks, dependencies, and build requirements
2. **Dockerfile Generation**: Create optimized, multi-stage Dockerfiles
3. **Docker Compose**: Generate comprehensive orchestration configurations
4. **Security Hardening**: Implement security best practices
5. **Optimization**: Minimize image size and build time
6. **Quality Assurance**: Review and validate Docker configurations

## Workflow - Analyze-Generate-Review-Optimize (AGRO)

### 1. Analyze
- Examine project structure and dependencies
- Identify framework and language versions
- Detect build tools and requirements
- Understand application architecture

### 2. Generate
- Create multi-stage Dockerfiles for production
- Generate docker-compose.yml for orchestration
- Include .dockerignore for optimization
- Add health checks and metadata

### 3. Review
- Validate Dockerfile syntax and best practices
- Check for security vulnerabilities
- Verify image optimization
- Ensure proper layer caching

### 4. Optimize
- Minimize image layers
- Use appropriate base images
- Implement caching strategies
- Add security hardening

## Docker Best Practices (Always Follow)

### Security
- Use official, minimal base images
- Run as non-root user
- Don't include secrets in images
- Keep dependencies up-to-date
- Use multi-stage builds to exclude build tools
- Scan for vulnerabilities

### Optimization
- Leverage layer caching
- Minimize layer count
- Use .dockerignore effectively
- Copy only necessary files
- Combine RUN commands wisely
- Use specific version tags

### Reliability
- Include health checks
- Set resource limits
- Handle signals properly
- Add restart policies
- Implement graceful shutdown

### Maintainability
- Use clear, descriptive labels
- Document build arguments
- Version your images
- Keep Dockerfiles simple and readable

## Tools Available
- `analyze_codebase`: Analyze project to detect tech stack
- `generate_dockerfile_with_llm`: Create intelligent Dockerfile
- `generate_docker_compose_with_llm`: Create docker-compose configuration
- `review_docker_configuration`: Review and optimize configurations
- File management tools for reading/writing files

## Process
1. **Always start by analyzing the codebase** using `analyze_codebase`
2. **Generate Dockerfile** based on analysis using `generate_dockerfile_with_llm`
3. **Generate docker-compose** if needed using `generate_docker_compose_with_llm`
4. **Review configurations** using `review_docker_configuration`
5. **Reflect on quality** and revise if confidence is low
6. **Provide clear deployment instructions**

## Output Format
Provide:
- Summary of analysis findings
- Generated Dockerfile with explanation
- Docker Compose configuration (if needed)
- Security considerations
- Optimization notes
- Build and run instructions

Begin by analyzing the codebase and then generating Docker configurations."""


def create_docker_agent() -> StateGraph:
    """
    Create Docker Agent with deep agent pattern and reflection.
    
    Returns:
        Compiled LangGraph with Docker agent nodes
    """
    
    # Get working directory for file tools
    import os
    root_dir = os.environ.get("PROJECT_ROOT", ".")
    file_tools = FileManagementToolkit(root_dir=root_dir).get_tools()
    
    # Combine all tools
    docker_tools = [
        analyze_codebase,
        generate_dockerfile,
        generate_docker_compose,
        generate_dockerfile_with_llm,
        generate_docker_compose_with_llm,
        review_docker_configuration,
    ]
    all_tools = file_tools + docker_tools
    
    # Create the agent with tools
    agent = create_agent(
        model=DEFAULT_MODEL,
        tools=all_tools,
        name="docker_agent",
        system_prompt=DOCKER_AGENT_PROMPT,
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
    async def docker_node(state: DockerAgentState) -> Dict[str, Any]:
        """Main Docker agent execution node."""
        try:
            logger.info("Docker Agent: Starting containerization workflow")
            
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
                "current_step": "docker_generation_complete",
            }
            
        except Exception as e:
            logger.error(f"Docker Agent error: {e}")
            errors = state.get("errors", [])
            return {
                **state,
                "last_error": str(e),
                "errors": errors + [{"error": str(e), "node": "docker_agent", "step": current_step}],
            }
    
    # Define reflection node wrapper
    async def reflect_node(state: DockerAgentState) -> Dict[str, Any]:
        """Reflection node for quality assurance."""
        logger.info("Docker Agent: Performing quality reflection")
        return reflection_node.reflect(state)
    
    # Define revision node
    async def revise_node(state: DockerAgentState) -> Dict[str, Any]:
        """Revision node to improve Docker configurations."""
        try:
            critique = state.get("critique", "")
            
            # Create revision prompt
            revision_message = f"""Based on this quality review, please revise the Docker configurations:

Critique: {critique}

Please improve the Dockerfile and docker-compose.yml to address these concerns."""
            
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
    async def recover_node(state: DockerAgentState) -> Dict[str, Any]:
        """Error recovery node."""
        logger.info("Docker Agent: Attempting error recovery")
        return error_recovery(state)
    
    # Routing functions
    def route_after_execution(state: DockerAgentState) -> str:
        """Route after main execution."""
        last_error = state.get("last_error")
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)
        
        # If there's an error and we haven't exceeded retries, try recovery
        if last_error and retry_count < max_retries:
            return "recover"
        
        # Otherwise, proceed to reflection
        return "reflect"
    
    def route_after_reflection(state: DockerAgentState) -> str:
        """Route after reflection."""
        should_revise = state.get("should_revise", False)
        revision_count = state.get("revision_count", 0)
        max_revisions = state.get("max_revisions", 3)
        
        # If we should revise and haven't exceeded limit, go to revision
        if should_revise and revision_count < max_revisions:
            return "revise"
        
        return "end"
    
    # Build the graph
    graph = StateGraph(DockerAgentState)
    
    # Add nodes
    graph.add_node("docker_agent", docker_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("revise", revise_node)
    graph.add_node("recover", recover_node)
    
    # Add edges
    graph.add_edge(START, "docker_agent")
    graph.add_conditional_edges(
        "docker_agent",
        route_after_execution,
        {
            "recover": "recover",
            "reflect": "reflect",
        }
    )
    graph.add_edge("recover", "docker_agent")  # Retry after recovery
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
agent = create_docker_agent().compile(name="docker_agent").with_config({"recursion_limit": 150})
