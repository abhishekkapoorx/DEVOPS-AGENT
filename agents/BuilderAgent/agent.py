
from langgraph_supervisor import create_supervisor

from llms import DEFAULT_MODEL

from .DockerAgent import agent as docker_agent
from .K8sAgent import agent as k8s_agent

agent = create_supervisor(
    supervisor_name="builder_agent",
    model=DEFAULT_MODEL,
    agents=[docker_agent, k8s_agent],
    prompt=(
        "You are a supervisor managing the following agents:\n"
        "- Docker Agent: Handles Docker operations, container builds, images, and registries\n"
        "- Kubernetes Agent: Handles K8s manifests, Helm charts, and cluster operations\n"
        "\n"
        "Instructions:\n"
        "- Assign work to one agent at a time, do not call agents in parallel.\n"
        "- Do not do any work yourself.\n"
        "- AUTONOMY: Instruct agents to use their tools and commands directly to complete build/deployment tasks independently.\n"
        "- Agents should NOT ask users to perform manual Docker or Kubernetes operations.\n"
        "- Route tasks: Docker/container tasks → Docker Agent, Kubernetes/cluster tasks → K8s Agent.\n"
        "- THINK-PLAN-ACT-REFLECT: Instruct agents to:\n"
        "  * THINK: Analyze build requirements, understand dependencies, identify potential issues\n"
        "  * PLAN: Create build/deployment strategy, identify required steps, consider rollback options\n"
        "  * ACT: Execute build commands/manifests, monitor progress, handle build failures\n"
        "  * REFLECT: Evaluate build success, identify optimization opportunities, adjust approach if needed"
    ),
    add_handoff_back_messages=True,
    output_mode="full_history",
).compile(name="builder_agent").with_config({"recursion_limit": 150})