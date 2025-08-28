from langchain_core.messages import AIMessage
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, START, END
from typing import Annotated, List, TypedDict

# States
class AWSAgent(TypedDict):
	messages: Annotated[List[str], add_messages]

# Tools
tools = []

# Agent
def agent_node(state: AWSAgent) -> AWSAgent:
	return {"messages": [AIMessage(content="GCPAgent: Not implemented yet.")]}

# Graph
graph = StateGraph(AWSAgent, input_schema=AWSAgent, output_schema=AWSAgent)
graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode(tools))

graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", tools_condition, "tools")
graph.add_edge("tools", "agent")

agent = graph.compile(name="gcp_agent")