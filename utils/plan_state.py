"""
Reusable planning state schema mixin for LangGraph.

This module provides state schema extensions that can be used with
any LangGraph workflow that needs planning capabilities.
"""

from typing import Optional, List
from typing_extensions import TypedDict, Annotated
from langgraph.prebuilt.chat_agent_executor import AgentState
from langgraph.graph.message import add_messages


class PlanningStateMixin(TypedDict):
    """Mixin state schema for planning functionality."""
    plan: Optional[str]  # Current plan
    plan_history: Annotated[List[str], lambda x, y: x + [y] if y else x]  # History of plan changes
    plan_version: int  # Version number of current plan


class PlanState(AgentState, PlanningStateMixin):
    """
    Complete state schema that includes both agent state and planning information.
    
    This is a ready-to-use state schema that can be used directly with LangGraph workflows.
    For custom state schemas, inherit from both your base state and PlanningStateMixin.
    
    Example:
        class MyCustomState(MyBaseState, PlanningStateMixin):
            # Your additional fields here
            pass
    """
    pass

