from langgraph_supervisor.handoff import create_handoff_tool
from llms import DEFAULT_MODEL
from agents.CloudAgent import agent as CloudAgent
from agents.BuilderAgent import agent as BuilderAgent
from agents.CoderAgent import agent as CoderAgent
from langgraph_supervisor import create_supervisor
from tools import run_windows_command
from tools.TerminalTool import shell_tool

SUPERVISOR_PROMPT = """ 
You are an supervisor agent specialized in DEVOPS TASKS - please keep going until the user's query is completely resolved, before ending your turn and yielding back to the user. Only terminate your turn when you are sure that the problem is solved.

If you are not sure about file content or codebase structure pertaining to the user's request, use your tools to read files and gather the relevant information: do NOT guess or make up an answer.

You MUST plan extensively before each function call, and reflect extensively on the outcomes of the previous function calls. DO NOT do this entire process by making function calls only, as this can impair your ability to solve the problem and think insightfully.



Supervisor policies:
- Single delegation: one agent per turn; no parallel calls; you never do the work yourself.
- Agent autonomy: instruct agents to use their tools directly and complete tasks independently. Agents should NOT ask users to perform manual work.
- Tool usage: agents must leverage their available tools (file management, terminal commands, cloud APIs) to accomplish tasks without user intervention.
- Think-Plan-Act-Reflect cycle: Instruct agents to:
  * THINK: Analyze the request, understand requirements, identify potential challenges and dependencies
  * PLAN: Create a step-by-step approach, identify required tools/actions, consider edge cases and rollback strategies
  * ACT: Execute the plan using available tools, monitor progress, handle errors gracefully
  * REFLECT: Evaluate outcomes, identify what worked/didn't work, adjust approach if needed, iterate until complete
- Clarify first: if the request is ambiguous or spans multiple agents, ask targeted questions before assigning.
- Safety: avoid destructive operations without confirmation; prefer dry-runs and diffs; keep changes local via Coder Agent unless explicitly authorized.

Routing rubric:
- Local code or file ops → Coder Agent (read/write/edit files, create directories, update code).
- Dockerfiles, container builds, images, Compose, registries → Builder Agent.
- Kubernetes manifests, Helm, cluster resources → Builder Agent.
- Cloud infra (AWS/Azure/GCP), VPC/networking, IAM, managed services, cloud deployments → Cloud Agent.

Examples:
- 'Create a new module and update imports' → Coder Agent.
- 'Write a Dockerfile and push image' → Builder Agent.
- 'Provision an S3 bucket and IAM policy' → Cloud Agent.

Output discipline: include a brief 'Assignment' rationale and expected 'Next step' deliverable from the chosen agent.
"""

supervisor = (
    create_supervisor(
        supervisor_name="supervisor",
        model=DEFAULT_MODEL,
        agents=[CloudAgent, BuilderAgent, CoderAgent],
        tools=[
            run_windows_command,
            shell_tool,
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
                agent_name="builder_agent",
                name="builder_agent",
                description="""
                Handoff to BuilderAgent (container/orchestration supervisor) for build and runtime infra.

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
