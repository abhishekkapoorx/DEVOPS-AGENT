from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, START, END
from typing import Annotated, List, Dict, Any
from typing_extensions import TypedDict
from langchain_community.agent_toolkits.file_management.toolkit import FileManagementToolkit
import os
import json

from llms import openai_models, groq_models, gemini_models
from tools.AgentTools.k8s_tools import (
    generate_k8s_manifests,
    generate_helm_chart,
    generate_k8s_service,
    analyze_k8s_requirements,
    generate_k8s_manifests_with_llm,
    generate_helm_chart_with_llm,
    review_k8s_configuration,
)

# States
class K8sAgent(TypedDict):
    messages: Annotated[List[str], add_messages]
    app_requirements: str
    manifests_content: str
    helm_chart_content: str
    user_requirements: str
    output_directory: str

# Tools
root_dir = r"C:\Users\Raghav Singla\Desktop\linux\pbl-agentic-deployment"
file_tools = FileManagementToolkit(root_dir=root_dir).get_tools()

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

# Initialize LLM
model = openai_models["gpt-4o-mini"]

# Tool Node
tool_node = ToolNode(all_tools)

# K8s Agent Node
async def k8s_agent_node(state: K8sAgent) -> K8sAgent:
    """K8s agent that can use all available tools."""
    last_message = state["messages"][-1] if state["messages"] else ""
    user_message = last_message.content if hasattr(last_message, 'content') else str(last_message)
    
    # Create a comprehensive prompt for the K8s agent
    system_prompt = """You are a Kubernetes expert agent specialized in generating and managing Kubernetes configurations. You have access to various tools to help users with their Kubernetes deployment needs.

## Your Capabilities:
1. **Analyze Requirements**: Analyze user requirements for Kubernetes deployment and extract key information
2. **Generate Manifests**: Create comprehensive Kubernetes manifests (Deployments, Services, ConfigMaps, Ingress, HPA, etc.)
3. **Generate Helm Charts**: Create complete Helm charts with templates, values, and Chart.yaml
4. **Review Configurations**: Review and provide optimization recommendations for Kubernetes configurations
5. **File Management**: Create, read, and manage files in the project directory

## Available Tools:
- `analyze_k8s_requirements`: Analyze user requirements for Kubernetes deployment
- `generate_k8s_manifests_with_llm`: Generate comprehensive Kubernetes manifests using LLM
- `generate_helm_chart_with_llm`: Generate complete Helm chart using LLM
- `review_k8s_configuration`: Review and optimize Kubernetes configurations
- `generate_k8s_manifests`: Generate basic Kubernetes manifests with parameters
- `generate_helm_chart`: Generate basic Helm chart with parameters
- `generate_k8s_service`: Generate individual Kubernetes service manifests
- File management tools for creating and managing files

## Workflow:
1. **Understand Requirements**: First analyze the user's requirements to understand what they need
2. **Generate Configurations**: Based on the analysis, generate appropriate Kubernetes manifests or Helm charts
3. **Review and Optimize**: Review the generated configurations and provide recommendations
4. **Provide Guidance**: Give clear instructions on how to deploy and use the generated configurations

## Best Practices:
- Always use production-ready configurations
- Implement security best practices (non-root users, resource limits, etc.)
- Include proper health checks and probes
- Configure auto-scaling appropriately
- Use proper labeling and selectors
- Provide comprehensive documentation

## Instructions:
- Use the LLM-based tools for complex, intelligent generation
- Use the parameter-based tools for quick, standard configurations
- Always review and optimize generated configurations
- Provide clear deployment instructions
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
        error_msg = f"Error in K8s agent: {str(e)}"
        return {"messages": [AIMessage(content=error_msg)]}

# Router function to determine next step
def should_continue(state: K8sAgent) -> str:
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
graph = StateGraph(K8sAgent, input_schema=K8sAgent, output_schema=K8sAgent)

# Add nodes
graph.add_node("k8s_agent", k8s_agent_node)
graph.add_node("tools", tool_node)

# Add edges
graph.add_edge(START, "k8s_agent")
graph.add_conditional_edges("k8s_agent", should_continue, {
    "tools": "tools",
    "end": END
})
graph.add_edge("tools", END)

# Compile the agent
agent = graph.compile(name="k8s_agent").with_config({"recursion_limit": 150})