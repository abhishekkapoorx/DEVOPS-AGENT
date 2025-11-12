"""
Reusable planning state schema for LangGraph.

This module provides state schema extensions that can be used with
any LangGraph workflow that needs planning capabilities.

Following LangChain documentation: custom state schemas must extend AgentState
as a TypedDict. AgentState already includes 'messages' and 'remaining_steps'.
"""

from typing import Optional, List
from typing_extensions import Annotated
from langgraph.prebuilt.chat_agent_executor import AgentState


class PlanState(AgentState):
    """
    Complete state schema that includes both agent state and planning information.
    
    This extends AgentState (which includes 'messages' and 'remaining_steps')
    and adds planning-specific fields. This follows the LangChain pattern for
    custom state schemas as shown in the documentation.
    
    Fields from AgentState:
    - messages: Annotated[List, add_messages] - Conversation messages
    - remaining_steps: int - Steps remaining in agent execution
    
    Additional planning fields:
    - plan: Optional[str] - Current plan
    - plan_history: List[str] - History of plan changes
    - plan_version: int - Version number of current plan
    - rag_context: Optional[str] - Retrieved context from RAG
    """
    plan: Optional[str]  # Current plan
    plan_history: Annotated[List[str], lambda x, y: x + [y] if y else x]  # History of plan changes
    plan_version: int  # Version number of current plan
    rag_context: Optional[str]  # Retrieved context from RAG


# Keep PlanningStateMixin for backwards compatibility if needed elsewhere
class PlanningStateMixin(PlanState):
    """
    Deprecated: Use PlanState directly instead.
    Kept for backwards compatibility.
    """
    pass

