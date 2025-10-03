from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, START, END
from typing import Annotated, List, Dict, Any
from typing_extensions import TypedDict
from langchain_community.agent_toolkits.file_management.toolkit import (
    FileManagementToolkit,
)
import os
import json

from llms import DEFAULT_MODEL, openai_models, groq_models, gemini_models
from tools.AgentTools.docker_tools import (
    analyze_codebase,
    generate_dockerfile,
    generate_docker_compose,
    generate_dockerfile_with_llm,
    generate_docker_compose_with_llm,
    review_docker_configuration,
)
from utils import _sanitize_path, _get_project_root_from_env

# States
class DockerAgent(TypedDict):
    messages: Annotated[List[str], add_messages]
    analysis_result: str
    dockerfile_content: str
    compose_content: str
    user_requirements: str
    output_directory: str
    project_root: str

# Tools
root_dir = r"C:\Users\Raghav Singla\Desktop\linux\pbl-agentic-deployment"
file_tools = FileManagementToolkit(root_dir=root_dir).get_tools()

docker_tools = [
    analyze_codebase,
    generate_dockerfile,
    generate_docker_compose,
    generate_dockerfile_with_llm,
    generate_docker_compose_with_llm,
    review_docker_configuration,
]

all_tools = file_tools + docker_tools

# Initialize LLM
model = openai_models["gpt-4o-mini"]

# Tool Node
tool_node = ToolNode(all_tools)

# Docker Agent Node
async def docker_agent_node(state: DockerAgent) -> DockerAgent:
    """Docker agent that can use all available tools."""
    last_message = state["messages"][-1] if state["messages"] else ""
    user_message = last_message.content if hasattr(last_message, 'content') else str(last_message)
    
    # Create a comprehensive prompt for the Docker agent
    system_prompt = """You are a Docker expert agent specialized in containerization and Docker-related tasks. You have access to various tools to help users with their Docker deployment needs.

## Your Capabilities:
1. **Analyze Codebase**: Analyze codebases to detect programming languages, frameworks, and dependencies
2. **Generate Dockerfiles**: Create production-ready Dockerfiles with multi-stage builds and security best practices
3. **Generate Docker Compose**: Create docker-compose.yml files for development and production environments
4. **Review Configurations**: Review and provide optimization recommendations for Docker configurations
5. **File Management**: Create, read, and manage files in the project directory

## Available Tools:
- `analyze_codebase`: Analyze a codebase to detect languages, frameworks, dependencies, and recommendations
- `generate_dockerfile_with_llm`: Generate production-ready Dockerfile using LLM based on analysis
- `generate_docker_compose_with_llm`: Generate comprehensive docker-compose.yml using LLM
- `review_docker_configuration`: Review and optimize Docker configurations
- `generate_dockerfile`: Generate basic Dockerfile with parameters
- `generate_docker_compose`: Generate basic docker-compose.yml with parameters
- File management tools for creating and managing files

## Workflow:
1. **Analyze Codebase**: First analyze the user's codebase to understand the project structure and requirements
2. **Generate Dockerfile**: Create a production-ready Dockerfile based on the analysis
3. **Generate Docker Compose**: Create a comprehensive docker-compose.yml file for orchestration
4. **Review and Optimize**: Review the generated configurations and provide recommendations
5. **Provide Guidance**: Give clear instructions on how to build and deploy the containers

## Best Practices:
- Use multi-stage builds for production optimization
- Implement security best practices (non-root users, minimal images, etc.)
- Avoid installing unnecessary packages in final images
- Use up-to-date minimal base images
- Include proper health checks and error handling
- Optimize for layer caching
- Generate appropriate .dockerignore files

## Instructions:
- Use the LLM-based tools for intelligent, context-aware generation
- Use the parameter-based tools for quick, standard configurations
- Always analyze the codebase first to understand the project
- Review and optimize all generated configurations
- Provide clear build and deployment instructions
- Ask for clarification if requirements are unclear

You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!"""
    
    # Create messages for the agent
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    try:
        # Use the model to generate a response
        response = await model.ainvoke(messages)
        return {"messages": [AIMessage(content=response.content)]}
    except Exception as e:
        error_msg = f"Error in Docker agent: {str(e)}"
        return {"messages": [AIMessage(content=error_msg)]}

# Router function to determine next step
def should_continue(state: DockerAgent) -> str:
    """Determine whether to continue to tools or end."""
    messages = state["messages"]
    last_message = messages[-1] if messages else None
    
    if last_message and hasattr(last_message, 'content'):
        content = last_message.content.lower()
        # If the message contains tool calls or action keywords, go to tools
        if any(keyword in content for keyword in ['action:', 'tool:', 'use ', 'call ']):
            return "tools"
    
    # Otherwise, end the conversation
    return "end"

# Create the graph
graph = StateGraph(DockerAgent, input_schema=DockerAgent, output_schema=DockerAgent)

# Add nodes
graph.add_node("docker_agent", docker_agent_node)
graph.add_node("tools", tool_node)

# Add edges
graph.add_edge(START, "docker_agent")
graph.add_conditional_edges("docker_agent", should_continue, {
    "tools": "tools",
    "end": END
})
graph.add_edge("tools", END)

# Compile the agent
agent = graph.compile(name="docker_agent").with_config({"recursion_limit": 150})
