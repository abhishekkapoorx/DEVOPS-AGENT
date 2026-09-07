"""
Thinker Agent - DeepAgents Architecture

This agent uses deepagents for strategic planning and reflection.
"""

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StoreBackend, FilesystemBackend
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import MemorySaver
from loguru import logger

from llms import DEFAULT_MODEL
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


def create_thinker_agent():
    """
    Create Thinker Agent using deepagents architecture.
    
    Returns:
        Compiled deep agent ready for invocation
    """
    logger.info("Creating Thinker Agent with deepagents architecture...")
    
    # Create backend factory
    def create_backend(runtime):
        """Create composite backend for file operations."""
        import os
        root_dir = os.path.abspath(os.getcwd())
        fs_backend = FilesystemBackend(root_dir=root_dir)
        return CompositeBackend(
            default=fs_backend,
            routes={
                "/memories/": StoreBackend(runtime),
            }
        )
    
    # Create checkpointer and store
    checkpointer = MemorySaver()
    store = InMemoryStore()
    
    # Create the deep agent
    agent = create_deep_agent(
        model=DEFAULT_MODEL,
        system_prompt=THINKER_AGENT_PROMPT,
        tools=[],  # Thinker agent primarily uses reasoning, not tools
        subagents=[],  # Thinker agent is standalone
        backend=create_backend,
        checkpointer=checkpointer,
        store=store,
    )
    
    logger.info("✅ Thinker Agent created with deepagents architecture!")
    
    return agent


# Create the agent instance
agent = create_thinker_agent()
