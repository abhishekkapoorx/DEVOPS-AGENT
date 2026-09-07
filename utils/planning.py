"""
Standardized Planning Node for LangGraph Agents

This module provides a reusable planning system that can be easily integrated
into any LangGraph workflow. It supports:
- Automatic plan generation using LLM
- Dynamic plan updates based on conversation context
- Configurable prompts and LLM models
- Extensible state schema
"""

from typing import Dict, Any, Optional, List, Callable
from langchain_core.language_models import LanguageModelLike
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate


class PlanningNode:
    """
    A standardized planning node that can be used as a pre_model_hook in LangGraph workflows.
    
    Usage:
        from utils.planning import PlanningNode
        from llms import DEFAULT_MODEL
        
        planning_hook = PlanningNode(
            model=DEFAULT_MODEL,
            min_messages_for_update=5,
            max_plan_versions=3
        )
        
        # Then use in create_supervisor or other graph builders:
        create_supervisor(..., pre_model_hook=planning_hook)
    """
    
    DEFAULT_PLAN_GENERATION_PROMPT = """You are a planning assistant for an automation system. 
Create a detailed, step-by-step plan to accomplish the user's task. 
Break down the task into clear, actionable steps considering:
- What agents or resources might be needed
- Dependencies between steps
- Potential risks or considerations
- Success criteria

Format your plan as a numbered list of steps."""
    
    DEFAULT_UPDATE_DECISION_PROMPT = """Based on the conversation context, determine if the plan needs to be updated.
Consider if:
- New information has emerged that changes the approach
- Obstacles or blockers have been encountered
- The task requirements have changed

Respond with just 'YES' or 'NO'."""
    
    DEFAULT_PLAN_UPDATE_PROMPT = """You are updating an existing plan based on new information from the conversation.
Review the original plan and the recent conversation context, then provide an updated plan.
If the original approach was sound, keep most steps but adjust details.
If issues were encountered, propose alternative approaches.
Format your updated plan as a numbered list of steps."""
    
    def __init__(
        self,
        model: LanguageModelLike,
        plan_generation_prompt: Optional[str] = None,
        update_decision_prompt: Optional[str] = None,
        plan_update_prompt: Optional[str] = None,
        min_messages_for_update: int = 5,
        max_plan_versions: int = 3,
        recent_context_window: int = 5,
        user_message_extractor: Optional[Callable[[List[Any]], Optional[str]]] = None,
    ):
        """
        Initialize the PlanningNode.
        
        Args:
            model: The LLM model to use for planning
            plan_generation_prompt: Custom prompt for initial plan generation
            update_decision_prompt: Custom prompt for deciding if plan should be updated
            plan_update_prompt: Custom prompt for updating existing plans
            min_messages_for_update: Minimum number of messages before checking for updates
            max_plan_versions: Maximum number of plan versions to create
            recent_context_window: Number of recent messages to consider for updates
            user_message_extractor: Optional custom function to extract user message from state
        """
        self.model = model
        self.plan_generation_prompt = plan_generation_prompt or self.DEFAULT_PLAN_GENERATION_PROMPT
        self.update_decision_prompt = update_decision_prompt or self.DEFAULT_UPDATE_DECISION_PROMPT
        self.plan_update_prompt = plan_update_prompt or self.DEFAULT_PLAN_UPDATE_PROMPT
        self.min_messages_for_update = min_messages_for_update
        self.max_plan_versions = max_plan_versions
        self.recent_context_window = recent_context_window
        self.user_message_extractor = user_message_extractor or self._default_user_message_extractor
    
    @staticmethod
    def _default_user_message_extractor(messages: List[Any]) -> Optional[str]:
        """Default function to extract user message from message list."""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                return msg.content
        return None
    
    def _generate_plan(self, user_message: str) -> str:
        """Generate a detailed plan using the LLM."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.plan_generation_prompt),
            ("human", "User task: {task}")
        ])
        
        chain = prompt | self.model
        response = chain.invoke({"task": user_message})
        return response.content
    
    def _should_update_plan(self, messages: list, plan_version: int) -> bool:
        """Use LLM to decide if the plan should be updated."""
        # Only check after some messages have been exchanged and plan version is within limit
        if len(messages) < self.min_messages_for_update or plan_version >= self.max_plan_versions:
            return False
        
        # Get recent messages for context
        recent_messages = messages[-self.recent_context_window:] if len(messages) > self.recent_context_window else messages
        conversation_context = "\n".join([
            f"{type(msg).__name__}: {getattr(msg, 'content', '')}" 
            for msg in recent_messages
        ])
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.update_decision_prompt),
            ("human", "Conversation context:\n{context}")
        ])
        
        try:
            chain = prompt | self.model
            response = chain.invoke({"context": conversation_context})
            return response.content.strip().upper() == "YES"
        except Exception:
            # Fallback to simple heuristic
            return len(messages) > (self.min_messages_for_update * 2) and plan_version < 2
    
    def _update_plan(self, original_plan: str, messages: list, plan_version: int) -> str:
        """Update the plan based on new information using the LLM."""
        recent_context = "\n".join([
            f"{type(msg).__name__}: {getattr(msg, 'content', '')}" 
            for msg in messages[-self.recent_context_window:]
        ])
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.plan_update_prompt),
            ("human", """Original Plan:
{original_plan}

Recent Conversation:
{context}

Provide the updated plan.""")
        ])
        
        try:
            chain = prompt | self.model
            response = chain.invoke({
                "original_plan": original_plan,
                "context": recent_context
            })
            return f"Updated Plan (Version {plan_version + 1}):\n\n{response.content}"
        except Exception:
            # Fallback to simple update
            return f"Updated Plan (Version {plan_version + 1}): Revising strategy based on progress..."
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main planning hook function that can be used as pre_model_hook.
        
        Expected state keys:
            - messages: List of messages (required)
            - plan: Optional[str] - Current plan
            - plan_version: int - Current plan version (defaults to 0)
            - plan_history: List[str] - History of plan changes (defaults to [])
        
        Returns:
            Updated state with plan information
        """
        messages = state.get("messages", [])
        plan = state.get("plan")
        plan_version = state.get("plan_version", 0)
        plan_history = state.get("plan_history", [])
        
        # Extract user message
        user_message = self.user_message_extractor(messages)
        
        # If no plan exists and there's a user message, create initial plan
        if not plan and user_message:
            initial_plan = self._generate_plan(user_message)
            initial_plan = f"Initial Plan:\n\n{initial_plan}"
            return {
                **state,  # Preserve all existing state
                "plan": initial_plan,
                "plan_version": 1,
                "plan_history": [initial_plan]
            }
        
        # Check if we need to update the plan
        if plan and self._should_update_plan(messages, plan_version):
            updated_plan = self._update_plan(plan, messages, plan_version)
            updated_plan_history = list(plan_history) + [updated_plan]
            return {
                **state,  # Preserve all existing state
                "plan": updated_plan,
                "plan_version": plan_version + 1,
                "plan_history": updated_plan_history
            }
        
        # No plan changes needed, return state as-is
        return state


# Convenience function for quick setup with defaults
def create_planning_hook(
    model: LanguageModelLike,
    **kwargs
) -> PlanningNode:
    """
    Convenience function to create a planning hook with default settings.
    
    Args:
        model: The LLM model to use for planning
        **kwargs: Additional arguments to pass to PlanningNode constructor
    
    Returns:
        Configured PlanningNode instance
    """
    return PlanningNode(model=model, **kwargs)

