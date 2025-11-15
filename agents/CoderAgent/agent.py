"""
Coder Agent - Deep Agent Pattern with Reflection

This deep agent specializes in file and code management with:
- Intelligent file operations
- Code quality assurance
- Multi-step code changes
- Self-reflection and validation
- Error recovery
"""

from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, HumanMessage
from typing import Dict, Any
from loguru import logger

from llms import DEFAULT_MODEL
from langchain_community.agent_toolkits.file_management.toolkit import (
    FileManagementToolkit,
)
from utils.deep_agent_state import CoderAgentState, create_initial_reflection_state
from utils.reflection import ReflectionNode, create_error_recovery_node
from utils.context_middleware import (
    bind_context_before_model,
    bind_context_for_tools,
)


CODER_AGENT_PROMPT = """# Coder Agent - File and Code Management Expert

## Role and Purpose
You are a coding agent specialized in file management and code-related tasks.
You ensure high-quality, well-structured code changes with proper validation.

## Core Capabilities
1. **File Operations**: Create, read, update, delete files and directories
2. **Code Writing**: Write clean, maintainable, well-documented code
3. **Code Review**: Review code quality and suggest improvements
4. **Refactoring**: Improve code structure and organization
5. **Validation**: Verify changes work correctly
6. **Quality Assurance**: Ensure code follows best practices

## Workflow - GAME Framework (Enhanced)

### Goal
- Understand the user's intent fully
- Define clear success criteria
- Consider edge cases and dependencies

### Actions
- Use file management tools effectively
- Make incremental, tested changes
- Document rationale for changes
- Follow language-specific best practices

### Method - Think-Plan-Act-Reflect-Validate (TPARV)

**Think**: Analyze the request
- What files need to be modified?
- What are the dependencies?
- What could go wrong?
- What's the best approach?

**Plan**: Create step-by-step plan
- Break down into atomic changes
- Order changes by dependencies
- Plan validation steps
- Consider rollback if needed

**Act**: Execute with precision
- Make one logical change at a time
- Write clear, self-documenting code
- Add appropriate comments
- Follow consistent style

**Reflect**: Self-critique
- Review the changes made
- Check for potential issues
- Verify completeness
- Assess code quality

**Validate**: Ensure correctness
- Verify files are created/modified correctly
- Check for syntax errors
- Ensure no breaking changes
- Confirm user requirements met

### Evaluation
- After completing changes, summarize what was done
- Highlight any important considerations
- Provide next steps if applicable
- Report confidence in changes

## Best Practices (Always Follow)

### Code Quality
- Write clean, readable code
- Follow language conventions
- Use descriptive names
- Add meaningful comments
- Keep functions focused and small
- Handle errors appropriately

### File Management
- Check if files exist before operations
- Create necessary directories
- Use appropriate file paths
- Preserve existing functionality
- Back up critical changes (mention in output)

### Safety
- Never delete files without explicit permission
- Confirm destructive operations
- Validate inputs
- Handle edge cases
- Report potential issues

### Documentation
- Document complex logic
- Add docstrings to functions/classes
- Update README files when needed
- Comment on non-obvious decisions

### Testing Mindset
- Think about test cases
- Consider edge cases
- Validate inputs and outputs
- Suggest tests if appropriate

## Communication
- Be clear and concise
- Explain your reasoning
- Ask for clarification when needed
- Provide context with changes
- Report both successes and issues

## Tools Available
- File reading (read, list, copy)
- File writing (write, append)
- File management (move, delete)
- Directory operations (list, create)

## Process for Code Changes
1. **Understand**: Read relevant files and understand context
2. **Plan**: Outline specific changes needed
3. **Implement**: Make changes methodically
4. **Review**: Self-critique the changes
5. **Revise**: Improve if confidence is low
6. **Report**: Summarize changes and next steps

Begin by understanding the user's request and working directory context."""


def create_coder_agent() -> StateGraph:
    """
    Create Coder Agent with deep agent pattern and reflection.
    
    Returns:
        Compiled LangGraph with Coder agent nodes
    """
    
    # Get working directory for file tools
    import os
    root_dir = os.environ.get("PROJECT_ROOT", ".")
    file_tools = FileManagementToolkit(root_dir=root_dir).get_tools()
    
    # Create the agent with tools
    agent = create_agent(
        model=DEFAULT_MODEL,
        tools=file_tools,
        name="coder_agent",
        system_prompt=CODER_AGENT_PROMPT,
        middleware=[bind_context_before_model, bind_context_for_tools],
    )
    
    # Create reflection node
    reflection_node = ReflectionNode(
        model=DEFAULT_MODEL,
        min_confidence_threshold=0.8,  # High bar for code quality
        max_reflection_iterations=3,
    )
    
    # Create error recovery node
    error_recovery = create_error_recovery_node(model=DEFAULT_MODEL, max_retries=3)
    
    # Define main agent node
    async def coder_node(state: CoderAgentState) -> Dict[str, Any]:
        """Main Coder agent execution node."""
        try:
            logger.info("Coder Agent: Starting file/code operations")
            
            # Update step tracking
            current_step = state.get("current_step", "initialization")
            completed_steps = state.get("completed_steps", [])
            
            # Invoke agent
            result = await agent.ainvoke(state)
            
            # Track successful execution
            completed_steps = list(completed_steps) + [current_step]
            
            # Extract file operations from messages if possible
            # This is a simple heuristic - in production, you might track this more explicitly
            messages = result.get("messages", [])
            files_modified = state.get("files_modified", [])
            files_created = state.get("files_created", [])
            
            return {
                **result,
                "completed_steps": completed_steps,
                "current_step": "coding_complete",
                "files_modified": files_modified,
                "files_created": files_created,
            }
            
        except Exception as e:
            logger.error(f"Coder Agent error: {e}")
            errors = state.get("errors", [])
            return {
                **state,
                "last_error": str(e),
                "errors": errors + [{"error": str(e), "node": "coder_agent", "step": current_step}],
            }
    
    # Define reflection node wrapper
    async def reflect_node(state: CoderAgentState) -> Dict[str, Any]:
        """Reflection node for code quality assurance."""
        logger.info("Coder Agent: Performing code quality reflection")
        return reflection_node.reflect(state)
    
    # Define revision node
    async def revise_node(state: CoderAgentState) -> Dict[str, Any]:
        """Revision node to improve code quality."""
        try:
            critique = state.get("critique", "")
            
            # Create revision prompt
            revision_message = f"""Based on this code review, please revise the code changes:

Critique: {critique}

Please improve the code to address these quality concerns."""
            
            messages = state.get("messages", [])
            messages = messages + [HumanMessage(content=revision_message)]
            
            # Re-invoke agent for revision
            result = await agent.ainvoke({**state, "messages": messages})
            
            return {
                **result,
                "should_revise": False,  # Reset after revision
                "current_step": "revision_complete",
            }
            
        except Exception as e:
            logger.error(f"Revision error: {e}")
            return state
    
    # Define error recovery node wrapper
    async def recover_node(state: CoderAgentState) -> Dict[str, Any]:
        """Error recovery node."""
        logger.info("Coder Agent: Attempting error recovery")
        return error_recovery(state)
    
    # Routing functions
    def route_after_execution(state: CoderAgentState) -> str:
        """Route after main execution."""
        last_error = state.get("last_error")
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)
        
        # If there's an error and we haven't exceeded retries, try recovery
        if last_error and retry_count < max_retries:
            return "recover"
        
        # Otherwise, proceed to reflection
        return "reflect"
    
    def route_after_reflection(state: CoderAgentState) -> str:
        """Route after reflection."""
        should_revise = state.get("should_revise", False)
        revision_count = state.get("revision_count", 0)
        max_revisions = state.get("max_revisions", 3)
        
        # If we should revise and haven't exceeded limit, go to revision
        if should_revise and revision_count < max_revisions:
            return "revise"
        
        return "end"
    
    # Build the graph
    graph = StateGraph(CoderAgentState)
    
    # Add nodes
    graph.add_node("coder_agent", coder_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("revise", revise_node)
    graph.add_node("recover", recover_node)
    
    # Add edges
    graph.add_edge(START, "coder_agent")
    graph.add_conditional_edges(
        "coder_agent",
        route_after_execution,
        {
            "recover": "recover",
            "reflect": "reflect",
        }
    )
    graph.add_edge("recover", "coder_agent")  # Retry after recovery
    graph.add_conditional_edges(
        "reflect",
        route_after_reflection,
        {
            "revise": "revise",
            "end": END,
        }
    )
    graph.add_edge("revise", "reflect")  # Re-reflect after revision
    
    return graph


# Create and compile the agent
agent = create_coder_agent().compile(name="coder_agent").with_config({"recursion_limit": 150})
