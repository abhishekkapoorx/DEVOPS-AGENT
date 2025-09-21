from langgraph_supervisor.handoff import create_handoff_tool

# Cloud Agent handoff tool
cloud_agent_handoff = create_handoff_tool(
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
)

# Docker/K8s Agent handoff tool
docker_k8s_handoff = create_handoff_tool(
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
)

# Coder Agent handoff tool
coder_agent_handoff = create_handoff_tool(
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

# List of all agent handoff tools
all_agent_handoffs = [
    cloud_agent_handoff,
    docker_k8s_handoff,
    coder_agent_handoff
]
