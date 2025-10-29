from typing import Optional, List
from typing_extensions import TypedDict, Annotated
from langgraph.prebuilt.chat_agent_executor import AgentState
from langgraph.graph.message import add_messages


class PlanState(AgentState):
    """State schema that includes planning information."""
    plan: Optional[str]  # Current plan
    plan_history: Annotated[List[str], lambda x, y: x + [y] if y else x]  # History of plan changes
    plan_version: int  # Version number of current plan

