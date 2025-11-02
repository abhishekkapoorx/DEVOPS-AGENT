from llms import DEFAULT_MODEL
from agents.CloudAgent import agent as CloudAgent
from agents.BuilderAgent import agent as BuilderAgent
from agents.CoderAgent import agent as CoderAgent
from langgraph_supervisor import create_supervisor
from tools import run_windows_command
from tools.TerminalTool import shell_tool
from tools.HandOffs.agent import (
    cloud_agent_handoff,
    docker_k8s_handoff,
    coder_agent_handoff
)
from plan_state import PlanState
from typing import Dict, Any
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate


def generate_plan_with_llm(user_message: str) -> str:
    """Generate a detailed plan using the LLM."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a planning assistant for a DevOps automation system. 
Create a detailed, step-by-step plan to accomplish the user's task. 
Break down the task into clear, actionable steps considering:
- What agents or resources might be needed
- Dependencies between steps
- Potential risks or considerations
- Success criteria

Format your plan as a numbered list of steps."""),
        ("human", "User task: {task}")
    ])
    
    chain = prompt | DEFAULT_MODEL
    response = chain.invoke({"task": user_message})
    return response.content


def should_update_plan(messages: list, plan_version: int) -> bool:
    """Use LLM to decide if the plan should be updated."""
    # Only check after some messages have been exchanged and plan version is still low
    if len(messages) < 5 or plan_version >= 3:
        return False
    
    # Get recent messages for context
    recent_messages = messages[-5:] if len(messages) > 5 else messages
    conversation_context = "\n".join([
        f"{type(msg).__name__}: {getattr(msg, 'content', '')}" 
        for msg in recent_messages
    ])
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Based on the conversation context, determine if the plan needs to be updated.
Consider if:
- New information has emerged that changes the approach
- Obstacles or blockers have been encountered
- The task requirements have changed

Respond with just 'YES' or 'NO'."""),
        ("human", "Conversation context:\n{context}")
    ])
    
    try:
        chain = prompt | DEFAULT_MODEL
        response = chain.invoke({"context": conversation_context})
        return response.content.strip().upper() == "YES"
    except:
        # Fallback to simple heuristic
        return len(messages) > 10 and plan_version < 2


def update_plan_with_llm(original_plan: str, messages: list, plan_version: int) -> str:
    """Update the plan based on new information using the LLM."""
    recent_context = "\n".join([
        f"{type(msg).__name__}: {getattr(msg, 'content', '')}" 
        for msg in messages[-5:]
    ])
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are updating an existing plan based on new information from the conversation.
Review the original plan and the recent conversation context, then provide an updated plan.
If the original approach was sound, keep most steps but adjust details.
If issues were encountered, propose alternative approaches.
Format your updated plan as a numbered list of steps."""),
        ("human", """Original Plan:
{original_plan}

Recent Conversation:
{context}

Provide the updated plan.""")
    ])
    
    try:
        chain = prompt | DEFAULT_MODEL
        response = chain.invoke({
            "original_plan": original_plan,
            "context": recent_context
        })
        return f"Updated Plan (Version {plan_version + 1}):\n\n{response.content}"
    except:
        # Fallback to simple update
        return f"Updated Plan (Version {plan_version + 1}): Revising strategy based on progress..."


def planning_hook(state: Dict[str, Any]) -> Dict[str, Any]:
    """Planning node that creates/updates a plan using LLM based on the current state."""
    messages = state.get("messages", [])
    plan = state.get("plan")
    plan_version = state.get("plan_version", 0)
    plan_history = state.get("plan_history", [])
    
    # Find the latest user message if any
    user_message = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_message = msg.content
            break
    
    # If no plan exists and there's a user message, create initial plan using LLM
    if not plan and user_message:
        initial_plan = generate_plan_with_llm(user_message)
        initial_plan = f"Initial Plan:\n\n{initial_plan}"
        return {
            "plan": initial_plan,
            "plan_version": 1,
            "plan_history": [initial_plan]
        }
    
    # Check if we need to update the plan using LLM decision
    if plan and should_update_plan(messages, plan_version):
        updated_plan = update_plan_with_llm(plan, messages, plan_version)
        updated_plan_history = list(plan_history) + [updated_plan]
        return {
            "plan": updated_plan,
            "plan_version": plan_version + 1,
            "plan_history": updated_plan_history
        }
    
    # No plan changes needed
    return state


SUPERVISOR_PROMPT = """ 
# Role and Objective
You supervise DevOps-related automation, orchestrating specialized agent workflows to fully resolve user requests before ending your turn.

You have access to a planning system that creates and updates task plans as needed. The plan is automatically managed and will evolve based on progress and changing requirements.

Begin with a concise checklist (3-7 bullets) of the conceptual steps required to resolve the user request before performing substantive work.

# Instructions
- Persist until the user's query is comprehensively solved.
- Do not return control until you verify completion.
- After each agent action, validate the result in 1-2 lines and proceed or self-correct if validation fails.
- If necessary information is missing (e.g., file contents, codebase structure), always use tool access to gather it. Never assume or guess.
- Use Think-Plan-Act-Reflect before each function call:
  * THINK: Analyze the request, determine requirements and challenges.
  * PLAN: Develop clear, sequenced steps and ensure rollback strategies.
  * ACT: Direct agents to use available tools to execute -- you delegate, never act directly or in parallel.
  * REFLECT: Inspect results, adapt approach, and keep iterating until task is fully done.
- Delegate only one agent per turn (no parallelization). You never perform the work personally.
- Ensure agents act autonomously with full tool access; agents must never ask the user for manual intervention.
- When safety is a concern (re: destructive actions), default to safe procedures: dry-runs, diffs, changes limited to local workspace unless explicitly authorized. For irreversible actions, require explicit user confirmation, and mask/anonymize any PII in outputs.
- If the request is ambiguous or crosses agent domains, clarify requirements with targeted questions before delegating. Attempt a first pass autonomously unless missing critical information; stop and ask if success criteria are unmet or conflicts arise.

# Routing Policies
- Send local code or file operations to `Coder Agent` (file editing, code changes, directory management).
- Send Docker/container/build tasks to `Builder Agent`.
- Direct Kubernetes or Helm tasks to `Builder Agent`.
- Route cloud infrastructure or resource provisioning (AWS, GCP, Azure, VPCs, IAM, managed services) to `Cloud Agent`.

# Output Discipline
- Every agent assignment must explain the rationale ('Assignment') and state the clear next expected deliverable ('Next step').

# Example Delegation
- 'Create a new module and update imports' → Coder Agent.
- 'Write a Dockerfile and push image' → docker-k8s-handler.
- 'Provision S3 bucket and IAM policy' → Cloud Agent.
"""

supervisor = (
    create_supervisor(
        supervisor_name="supervisor",
        model=DEFAULT_MODEL,
        agents=[CloudAgent, BuilderAgent, CoderAgent],
        tools=[
            run_windows_command,
            shell_tool,
            cloud_agent_handoff,
            docker_k8s_handoff,
            coder_agent_handoff
        ],
        prompt=SUPERVISOR_PROMPT,
        add_handoff_back_messages=True,
        output_mode="last_message",
        state_schema=PlanState,
        pre_model_hook=planning_hook
    )
    .compile(name="supervisor")
    .with_config({"recursion_limit": 150})
)
