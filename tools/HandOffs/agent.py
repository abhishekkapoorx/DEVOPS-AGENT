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
    - Includes self-reflection and code quality validation
    - Verifies changes and returns with a concise summary of edits
    """
)

# Thinker Agent handoff tool
thinker_agent_handoff = create_handoff_tool(
    agent_name="thinker_agent",
    name="thinker_agent",
    description="""
    Handoff to ThinkerAgent for strategic planning and high-level analysis.

    Scope:
    - Strategic analysis and planning for complex problems
    - Risk assessment and mitigation strategy development
    - Evaluation of multiple solution approaches
    - Decision rationale and architectural guidance
    - Complex problem decomposition
    - Success criteria definition

    Behavior:
    - Provides deep strategic thinking and reasoning
    - Evaluates alternatives and recommends optimal approaches
    - Includes self-reflection on analysis quality
    - Returns with clear recommendations and rationale
    """
)

# Watcher Agent handoff tool
watcher_agent_handoff = create_handoff_tool(
    agent_name="watcher_agent",
    name="watcher_agent",
    description="""
    Handoff to WatcherAgent for monitoring and observability.

    Scope:
    - System health monitoring and status checks
    - Performance metrics collection and analysis
    - Anomaly detection across agent operations
    - Alert generation for issues
    - Observability recommendations
    - Agent coordination monitoring

    Behavior:
    - Monitors agent and system performance
    - Detects anomalies and generates alerts
    - Provides insights on system health
    - Returns with health status, metrics, and recommendations
    """
)


# List of all agent handoff tools
all_agent_handoffs = [
    thinker_agent_handoff,
    coder_agent_handoff,
    docker_k8s_handoff,
    cloud_agent_handoff,
    watcher_agent_handoff,
]
