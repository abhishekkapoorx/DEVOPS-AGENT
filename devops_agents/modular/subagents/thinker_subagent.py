"""
Thinker Subagent - Wraps ThinkerAgent for DeepAgents integration

Uses the existing ThinkerAgent for strategic planning and reflection.
"""

from agents.ThinkerAgent.agent import agent as thinker_agent


def create_thinker_subagent():
    """
    Create thinker subagent using the existing ThinkerAgent.
    
    ThinkerAgent specializes in:
    - High-level strategic analysis and planning
    - Risk assessment and mitigation strategies
    - Alternative approach evaluation
    - Decision rationale and reasoning
    - Success criteria definition
    
    Uses TPARE Framework:
    - Think: Deep analysis of problem space
    - Plan: Strategic planning with objectives
    - Act: Coordinate with other agents
    - Reflect: Review outcomes and improve
    - Evolve: Continuous learning and adaptation
    
    Returns:
        Compiled LangGraph graph for strategic thinking
    """
    return thinker_agent

