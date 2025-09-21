from langgraph_supervisor.handoff import create_handoff_tool
from llms import DEFAULT_MODEL
from agents.CloudAgent import agent as CloudAgent
from agents.BuilderAgent import agent as BuilderAgent
from agents.CoderAgent import agent as CoderAgent
from langgraph_supervisor import create_supervisor
from tools import run_windows_command


SUPERVISOR_PROMPT = """ 
Developer: # Role and Objective
You supervise DevOps-related automation, orchestrating specialized agent workflows to fully resolve user requests before ending your turn.

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
            create_handoff_tool(
                agent_name="cloud_agent",
                name="cloud_agent",
                description="""
                Handoff to CloudAgent (cloud supervisor) for cloud infrastructure tasks.

                Scope:
                - Provisioning and managing resources on AWS, Azure, and GCP
                - IAM/policies, networking (VPC/VNet/VPC), storage, compute, databases
                - Deploying managed services and performing cloud-native operations

                Behavior:
                - Routes tasks to the appropriate cloud sub-agent (AWS/Azure/GCP)
                - Operates autonomously using provider APIs and tools; no manual user steps
                - Provides assignment rationale and next-step deliverables on handoff back
                """
            ),
            create_handoff_tool(
                agent_name="docker-k8s-handler",
                name="docker-k8s-handler",
                description="""
                Handoff to docker-k8s-handler (container/orchestration supervisor) for build and runtime infra.

                Scope:
                - Dockerfiles, image builds, registries, Compose setups
                - Kubernetes manifests, Helm charts, deployments, services, ingress
                - Runtime config: env, secrets, volumes, networking, autoscaling, observability

                Behavior:
                - Routes tasks to Docker or Kubernetes sub-agents as appropriate
                - Operates autonomously using CLI/APIs; avoids requiring manual user steps
                - Returns with rationale and concrete next-step deliverables after completion
                """
            ),
            create_handoff_tool(
                agent_name="coder_agent",
                name="coder_agent",
                description="""
                Handoff to CoderAgent for local code and file operations.

                Scope:
                - Create, read, edit, delete, and organize files within the workspace
                - Refactors, boilerplate generation, code updates, and small utilities
                - Project scaffolding and module/file restructuring

                Behavior:
                - Uses file management tools autonomously; no manual user steps
                - Verifies changes and returns with a concise summary of edits
                """
            )
        ],
        prompt=SUPERVISOR_PROMPT,
        add_handoff_back_messages=True,
        output_mode="full_history",
    )
    .compile(name="supervisor")
    .with_config({"recursion_limit": 150})
)
