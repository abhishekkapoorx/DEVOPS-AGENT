from langchain_core.messages import AIMessage
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, START, END
from typing import Annotated, List, TypedDict

# States
class AzureAgent(TypedDict):
	messages: Annotated[List[str], add_messages]

# Tools
tools = []

# Agent
def agent_node(state: AzureAgent) -> AzureAgent:
	return {"messages": [AIMessage(content="AzureAgent: Not implemented yet.")]}

# Graph
graph = StateGraph(AzureAgent, input_schema=AzureAgent, output_schema=AzureAgent)
graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode(tools))

graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", tools_condition, "tools")
graph.add_edge("tools", "agent")

agent = graph.compile(name="azure_agent").with_config({"recursion_limit": 150})