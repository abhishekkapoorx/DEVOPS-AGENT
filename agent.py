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
from utils.plan_state import PlanState
from utils.planning import create_planning_hook
from utils.rag import get_pinecone_retriever, create_rag_context_hook
from utils.context import AgentContext, set_working_directory_context
from utils.context_middleware import (
    bind_context_before_model,
    bind_context_for_tools,
)

from loguru import logger

# Create planning hook with default settings
planning_hook = create_planning_hook(
    model=DEFAULT_MODEL,
    min_messages_for_update=5,
    max_plan_versions=3,
)

# Optional RAG hook sourced from Pinecone
rag_retriever = get_pinecone_retriever()
if rag_retriever:
    logger.info("Pinecone retriever loaded for RAG context.")
    rag_hook = create_rag_context_hook(rag_retriever)

    def combined_pre_model_hook(state):
        updated_state = rag_hook(state)
        updated_state = planning_hook(updated_state)
        if "remaining_steps" in updated_state:
            updated_state = dict(updated_state)
            updated_state.pop("remaining_steps", None)
        return updated_state

else:
    logger.warning("Pinecone retriever unavailable; proceeding without RAG context.")

    def combined_pre_model_hook(state):
        updated_state = planning_hook(state)
        if "remaining_steps" in updated_state:
            updated_state = dict(updated_state)
            updated_state.pop("remaining_steps", None)
        return updated_state


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

# **Information Gathering**: If you lack project information (file contents, codebase structure, dependencies, configuration), you MUST actively gather it using available tools BEFORE making assumptions:
  * Use `grep` or search commands to find relevant code, configurations, or references
  * Use directory listing tools (`ls`, `list_dir`, etc.) to explore project structure
  * Read relevant files to understand context, dependencies, and existing patterns
  * Search for similar implementations or patterns in the codebase
  * Never assume file locations, dependencies, or project structure - always verify through tools

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
        middleware=[bind_context_before_model, bind_context_for_tools],
        pre_model_hook=combined_pre_model_hook
    )
    .compile(name="supervisor")
    .with_config({"recursion_limit": 150})
)
