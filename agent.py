from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from typing import Annotated, TypedDict, List
from llms import groq_models


# States
class AgentState(TypedDict):
    messages: Annotated[List[str], add_messages]

class AgentInputState(TypedDict):
    messages: Annotated[List[str], add_messages]

class AgentOutputState(TypedDict):
    messages: Annotated[List[str], add_messages]


def agent_node(state: AgentState) -> AgentState:
    return {"messages": groq_models["openai/gpt-oss-20b"].invoke(state["messages"])}

graph = StateGraph(AgentState, input_schema=AgentInputState, output_schema=AgentOutputState)

graph.add_node("agent", agent_node)

graph.add_edge(START, "agent")
graph.add_edge("agent", END)

workflow = graph.compile()

# workflow.invoke({"messages": ["Hello, how are you?"]})





