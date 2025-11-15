"""
Reflection and Self-Critique Mechanisms for Deep Agents

This module provides reflection capabilities that allow agents to:
- Critique their own work
- Evaluate confidence in their outputs
- Decide whether to revise their approach
- Learn from mistakes and improve over time
"""

from typing import Dict, Any, Optional, List, Callable
from langchain_core.language_models import LanguageModelLike
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger


class ReflectionNode:
    """
    Reflection node that enables agents to critique and improve their work.
    
    This implements the reflection pattern from LangChain's agent documentation,
    where agents can evaluate their outputs and decide whether to revise.
    """
    
    DEFAULT_REFLECTION_PROMPT = """You are a critical evaluator reviewing the work of an AI agent.
    
Analyze the agent's recent actions and outputs, considering:
1. **Correctness**: Are the outputs accurate and appropriate?
2. **Completeness**: Does it fully address the user's request?
3. **Quality**: Is the work of high quality and following best practices?
4. **Efficiency**: Could this be done more efficiently?
5. **Safety**: Are there any security or safety concerns?

Provide:
- A confidence score (0.0 to 1.0) indicating how confident you are in the work
- Specific critique pointing out issues or areas for improvement
- A recommendation on whether the agent should revise its work (YES/NO)

Format your response as:
CONFIDENCE: <score>
SHOULD_REVISE: <YES/NO>
CRITIQUE: <detailed critique>"""
    
    DEFAULT_REVISION_PROMPT = """Based on the following critique of your previous work, 
provide an improved version that addresses the identified issues.

Previous Work:
{previous_work}

Critique:
{critique}

Provide your revised approach or output."""
    
    def __init__(
        self,
        model: LanguageModelLike,
        reflection_prompt: Optional[str] = None,
        revision_prompt: Optional[str] = None,
        min_confidence_threshold: float = 0.7,
        max_reflection_iterations: int = 3,
    ):
        """
        Initialize the ReflectionNode.
        
        Args:
            model: The LLM model to use for reflection
            reflection_prompt: Custom prompt for reflection/critique
            revision_prompt: Custom prompt for generating revisions
            min_confidence_threshold: Minimum confidence to avoid revision
            max_reflection_iterations: Maximum number of reflection cycles
        """
        self.model = model
        self.reflection_prompt = reflection_prompt or self.DEFAULT_REFLECTION_PROMPT
        self.revision_prompt = revision_prompt or self.DEFAULT_REVISION_PROMPT
        self.min_confidence_threshold = min_confidence_threshold
        self.max_reflection_iterations = max_reflection_iterations
    
    def _extract_work_summary(self, state: Dict[str, Any]) -> str:
        """Extract a summary of the agent's recent work from state."""
        messages = state.get("messages", [])
        recent_messages = messages[-5:] if len(messages) > 5 else messages
        
        work_summary = []
        for msg in recent_messages:
            if isinstance(msg, AIMessage):
                content = msg.content if hasattr(msg, 'content') else str(msg)
                work_summary.append(f"Agent: {content}")
        
        # Include intermediate results if available
        intermediate_results = state.get("intermediate_results", {})
        if intermediate_results:
            work_summary.append(f"\nIntermediate Results: {intermediate_results}")
        
        return "\n".join(work_summary)
    
    def reflect(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform reflection on the agent's work.
        
        Args:
            state: Current agent state
            
        Returns:
            Updated state with reflection results
        """
        # Check if we've hit max iterations
        revision_count = state.get("revision_count", 0)
        if revision_count >= self.max_reflection_iterations:
            logger.info(f"Max reflection iterations ({self.max_reflection_iterations}) reached")
            return {
                **state,
                "should_revise": False,
                "critique": "Maximum reflection iterations reached. Proceeding with current work."
            }
        
        # Extract work to reflect on
        work_summary = self._extract_work_summary(state)
        if not work_summary.strip():
            logger.debug("No work to reflect on yet")
            return state
        
        # Create reflection prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.reflection_prompt),
            ("human", "Review this work:\n\n{work}")
        ])
        
        try:
            # Get reflection from model
            chain = prompt | self.model
            response = chain.invoke({"work": work_summary})
            reflection_text = response.content
            
            # Parse reflection response
            confidence = self._parse_confidence(reflection_text)
            should_revise = self._parse_should_revise(reflection_text)
            critique = self._parse_critique(reflection_text)
            
            # Create reflection record
            reflection = {
                "iteration": revision_count + 1,
                "confidence": confidence,
                "should_revise": should_revise,
                "critique": critique,
                "work_reviewed": work_summary[:200] + "...",  # Truncate for storage
            }
            
            # Determine if revision is needed
            needs_revision = should_revise and confidence < self.min_confidence_threshold
            
            logger.info(
                f"Reflection complete - Confidence: {confidence:.2f}, "
                f"Should Revise: {needs_revision}"
            )
            
            # Update state
            reflections = state.get("reflections", [])
            return {
                **state,
                "reflections": reflections + [reflection],
                "critique": critique,
                "confidence_score": confidence,
                "should_revise": needs_revision,
                "revision_count": revision_count + (1 if needs_revision else 0),
            }
            
        except Exception as e:
            logger.error(f"Reflection failed: {e}")
            return {
                **state,
                "should_revise": False,
                "critique": f"Reflection error: {str(e)}",
                "confidence_score": 0.5,  # Neutral confidence
            }
    
    def _parse_confidence(self, text: str) -> float:
        """Parse confidence score from reflection text."""
        try:
            for line in text.split('\n'):
                if line.strip().startswith('CONFIDENCE:'):
                    score_str = line.split(':', 1)[1].strip()
                    return float(score_str)
        except (ValueError, IndexError):
            pass
        return 0.5  # Default neutral confidence
    
    def _parse_should_revise(self, text: str) -> bool:
        """Parse should_revise decision from reflection text."""
        try:
            for line in text.split('\n'):
                if line.strip().startswith('SHOULD_REVISE:'):
                    decision = line.split(':', 1)[1].strip().upper()
                    return decision == 'YES'
        except IndexError:
            pass
        return False  # Default to not revising
    
    def _parse_critique(self, text: str) -> str:
        """Parse critique text from reflection response."""
        try:
            if 'CRITIQUE:' in text:
                critique = text.split('CRITIQUE:', 1)[1].strip()
                return critique
        except IndexError:
            pass
        return text  # Return full text as fallback


def create_reflection_hook(
    model: LanguageModelLike,
    **kwargs
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """
    Convenience function to create a reflection hook.
    
    Args:
        model: The LLM model to use for reflection
        **kwargs: Additional arguments to pass to ReflectionNode
        
    Returns:
        Configured reflection function
    """
    reflection_node = ReflectionNode(model=model, **kwargs)
    return reflection_node.reflect


def should_continue_or_reflect(state: Dict[str, Any]) -> str:
    """
    Decision function for routing: continue with work or reflect/revise.
    
    This can be used as a conditional edge in LangGraph to determine
    whether to route to a reflection node or continue execution.
    
    Args:
        state: Current agent state
        
    Returns:
        "reflect" if reflection is needed, "continue" otherwise
    """
    # Check if we should reflect based on state flags
    should_revise = state.get("should_revise", False)
    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", 3)
    
    # Reflect if we need to revise and haven't exceeded max iterations
    if should_revise and revision_count < max_revisions:
        return "reflect"
    
    return "continue"


def create_error_recovery_node(
    model: LanguageModelLike,
    max_retries: int = 3,
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """
    Create an error recovery node that analyzes errors and proposes recovery strategies.
    
    Args:
        model: The LLM model to use for error analysis
        max_retries: Maximum number of retry attempts
        
    Returns:
        Error recovery function
    """
    
    ERROR_ANALYSIS_PROMPT = """Analyze the following error and provide a recovery strategy.

Error: {error}

Context: {context}

Provide:
1. Root cause analysis
2. Recommended recovery strategy
3. Alternative approach if retry fails

Format as:
CAUSE: <brief root cause>
STRATEGY: <recovery strategy>
FALLBACK: <alternative approach>"""
    
    def analyze_and_recover(state: Dict[str, Any]) -> Dict[str, Any]:
        last_error = state.get("last_error")
        retry_count = state.get("retry_count", 0)
        
        if not last_error or retry_count >= max_retries:
            return state
        
        try:
            # Analyze error
            prompt = ChatPromptTemplate.from_messages([
                ("system", ERROR_ANALYSIS_PROMPT),
                ("human", "Analyze this error")
            ])
            
            context = state.get("working_memory", {})
            chain = prompt | model
            response = chain.invoke({
                "error": last_error,
                "context": str(context)
            })
            
            # Extract recovery strategy
            analysis = response.content
            
            # Update state with recovery information
            errors = state.get("errors", [])
            errors.append({
                "error": last_error,
                "analysis": analysis,
                "retry_count": retry_count,
            })
            
            return {
                **state,
                "errors": errors,
                "retry_count": retry_count + 1,
                "fallback_strategy": analysis,
            }
            
        except Exception as e:
            logger.error(f"Error recovery analysis failed: {e}")
            return state
    
    return analyze_and_recover

