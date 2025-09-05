from langchain_core.messages import AIMessage
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, START, END
from typing import Annotated, List, TypedDict

# States
class DockerAgent(TypedDict):
	messages: Annotated[List[str], add_messages]

# Tools
tools = []

# Agent
def agent_node(state: DockerAgent) -> DockerAgent:
	return {"messages": [AIMessage(content="DockerAgent: Not implemented yet.")]}

# Graph
graph = StateGraph(DockerAgent, input_schema=DockerAgent, output_schema=DockerAgent)
graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode(tools))

graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", tools_condition, "tools")
graph.add_edge("tools", "agent")

agent = graph.compile(name="docker_agent").with_config({"recursion_limit": 150})