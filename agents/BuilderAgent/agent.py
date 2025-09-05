
from langgraph_supervisor import create_supervisor

from llms import DEFAULT_MODEL

from .DockerAgent import agent as docker_agent
from .K8sAgent import agent as k8s_agent

agent = create_supervisor(
    name="builder_agent",
    model=DEFAULT_MODEL,
    agents=[docker_agent, k8s_agent],
    prompt=(
        "You are a supervisor managing the following agents:\n"
        "- a docker agent. Assign docker-related tasks to this agent\n"
        "- a k8s agent. Assign k8s-related tasks to this agent\n"
        "Assign work to one agent at a time, do not call agents in parallel.\n"
        "Do not do any work yourself."
    ),
    add_handoff_back_messages=True,
    output_mode="full_history",
).compile(name="builder_agent").with_config({"recursion_limit": 150})