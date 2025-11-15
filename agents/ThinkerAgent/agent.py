"""
Thinker Agent - Strategic Planning and Reflection

This deep agent specializes in:
- High-level strategic analysis and planning
- Risk assessment and mitigation strategies
- Alternative approach evaluation
- Decision rationale and reasoning
- Success criteria definition
"""

from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from typing import Dict, Any
from loguru import logger

from llms import DEFAULT_MODEL
from utils.deep_agent_state import ThinkerAgentState, create_initial_reflection_state
from utils.reflection import ReflectionNode, should_continue_or_reflect
from utils.context_middleware import (
    bind_context_before_model,
    bind_context_for_tools,
)


THINKER_AGENT_PROMPT = """# Thinker Agent - Strategic Planning and Reflection

## Role and Purpose
You are a strategic thinking agent specialized in high-level analysis, planning, and reflection.
Your role is to think deeply about complex problems and provide strategic guidance.

## Core Capabilities
1. **Strategic Analysis**: Break down complex problems into manageable components
2. **Risk Assessment**: Identify potential risks and propose mitigation strategies
3. **Alternative Approaches**: Evaluate multiple solution paths and recommend the best
4. **Decision Rationale**: Provide clear reasoning for recommendations
5. **Success Criteria**: Define measurable criteria for success
6. **Meta-Reflection**: Reflect on the team's approach and suggest improvements

## Methodology - TPARE Framework
**Think**: Deep analysis of the problem space
- Consider all stakeholders and their needs
- Identify constraints, dependencies, and assumptions
- Map out the problem landscape

**Plan**: Strategic planning
- Define clear objectives and success criteria
- Break down into phases with milestones
- Identify resources and timeline
- Plan for contingencies

**Analyze**: Evaluate options
- Generate multiple approaches
- Assess pros/cons of each
- Consider short-term and long-term implications
- Evaluate risk vs. reward

**Recommend**: Provide clear recommendations
- Select optimal approach with rationale
- Prioritize actions
- Define decision points
- Set success metrics

**Evaluate**: Continuous reflection
- Monitor progress against plan
- Identify deviations and adjust
- Learn from outcomes
- Share insights with team

## Output Format
Structure your responses as:

### Strategic Analysis
[High-level analysis of the situation]

### Risk Assessment
[Key risks and mitigation strategies]

### Recommended Approach
[Preferred solution with clear rationale]

### Alternative Approaches
[Other viable options to consider]

### Success Criteria
[How to measure success]

### Next Steps
[Immediate actionable steps]

## Principles
- Think long-term, not just immediate solutions
- Consider second-order effects
- Value simplicity and elegance
- Prioritize maintainability and scalability
- Emphasize security and reliability
- Always provide rationale for recommendations

Begin by awaiting strategic questions or planning requests."""


def create_thinker_agent() -> StateGraph:
    """
    Create the Thinker Agent with reflection capabilities.
    
    Returns:
        Compiled LangGraph with thinker agent nodes
    """
    
    # Create the agent with strategic thinking capabilities
    agent = create_agent(
        model=DEFAULT_MODEL,
        tools=[],  # Thinker agent primarily uses reasoning, not tools
        name="thinker_agent",
        system_prompt=THINKER_AGENT_PROMPT,
        middleware=[bind_context_before_model, bind_context_for_tools],
    )
    
    # Create reflection node for self-critique
    reflection_node = ReflectionNode(
        model=DEFAULT_MODEL,
        min_confidence_threshold=0.8,  # High bar for strategic thinking
        max_reflection_iterations=3,
    )
    
    # Define agent node
    async def thinker_node(state: ThinkerAgentState) -> Dict[str, Any]:
        """Main thinker agent node."""
        try:
            logger.info("Thinker Agent: Starting strategic analysis")
            
            # Invoke the agent
            result = await agent.ainvoke(state)
            
            # Extract strategic components from response
            messages = result.get("messages", [])
            if messages:
                last_message = messages[-1]
                content = last_message.content if hasattr(last_message, 'content') else str(last_message)
                
                # Parse strategic analysis (simple heuristic)
                strategic_analysis = content
                
                # Update working memory with analysis
                working_memory = state.get("working_memory", {})
                working_memory["latest_strategic_analysis"] = strategic_analysis
                
                return {
                    **result,
                    "strategic_analysis": strategic_analysis,
                    "working_memory": working_memory,
                    "current_step": "strategic_analysis_complete",
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Thinker Agent error: {e}")
            return {
                **state,
                "last_error": str(e),
                "errors": state.get("errors", []) + [{"error": str(e), "node": "thinker"}],
            }
    
    # Define reflection node wrapper
    async def reflect_node(state: ThinkerAgentState) -> Dict[str, Any]:
        """Reflection node for self-critique."""
        logger.info("Thinker Agent: Performing self-reflection")
        return reflection_node.reflect(state)
    
    # Define revision node
    async def revise_node(state: ThinkerAgentState) -> Dict[str, Any]:
        """Revision node to improve strategic analysis."""
        try:
            critique = state.get("critique", "")
            strategic_analysis = state.get("strategic_analysis", "")
            
            revision_prompt = f"""Based on this critique of your strategic analysis, provide an improved version.

Previous Analysis:
{strategic_analysis}

Critique:
{critique}

Provide your revised strategic analysis addressing the critique."""
            
            messages = state.get("messages", [])
            messages = messages + [HumanMessage(content=revision_prompt)]
            
            result = await agent.ainvoke({**state, "messages": messages})
            
            return {
                **result,
                "should_revise": False,  # Reset after revision
            }
            
        except Exception as e:
            logger.error(f"Revision error: {e}")
            return state
    
    # Routing function
    def route_after_reflection(state: ThinkerAgentState) -> str:
        """Determine whether to revise or finish."""
        should_revise = state.get("should_revise", False)
        revision_count = state.get("revision_count", 0)
        max_revisions = state.get("max_revisions", 3)
        
        if should_revise and revision_count < max_revisions:
            return "revise"
        return "end"
    
    # Build the graph
    graph = StateGraph(ThinkerAgentState)
    
    # Add nodes
    graph.add_node("think", thinker_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("revise", revise_node)
    
    # Add edges
    graph.add_edge(START, "think")
    graph.add_edge("think", "reflect")
    graph.add_conditional_edges(
        "reflect",
        route_after_reflection,
        {
            "revise": "revise",
            "end": END,
        }
    )
    graph.add_edge("revise", "reflect")
    
    return graph


# Create and compile the agent
agent = create_thinker_agent().compile(name="thinker_agent").with_config({"recursion_limit": 150})

