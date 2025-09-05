from langchain_core.messages import AIMessage
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, START, END
from typing import Annotated, List, TypedDict

# States
class K8sAgent(TypedDict):
	messages: Annotated[List[str], add_messages]

# Tools
tools = []

# Agent
def agent_node(state: K8sAgent) -> K8sAgent:
	return {"messages": [AIMessage(content="K8sAgent: Not implemented yet.")]}

# Graph
graph = StateGraph(K8sAgent, input_schema=K8sAgent, output_schema=K8sAgent)
graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode(tools))

graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", tools_condition, "tools")
graph.add_edge("tools", "agent")

agent = graph.compile(name="k8s_agent").with_config({"recursion_limit": 150})