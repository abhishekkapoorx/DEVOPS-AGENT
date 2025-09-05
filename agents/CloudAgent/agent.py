
from langgraph_supervisor import create_supervisor

from .AWSAgent import agent as aws_agent
from .AzureAgent import agent as azure_agent
from .GCPAgent import agent as gcp_agent
from llms import DEFAULT_MODEL

agent = create_supervisor(
    name="cloud_agent",
    model=DEFAULT_MODEL,
    agents=[aws_agent, azure_agent, gcp_agent],
    prompt=(
        "You are a supervisor managing the following agents:\n"
        "- AWS Agent: Handles AWS cloud operations, provisioning, and management\n"
        "- Azure Agent: Handles Azure cloud operations, provisioning, and management\n"
        "- GCP Agent: Handles Google Cloud operations, provisioning, and management\n"
        "\n"
        "Instructions:\n"
        "- Assign work to one agent at a time, do not call agents in parallel.\n"
        "- Do not do any work yourself.\n"
        "- AUTONOMY: Instruct agents to use their tools and APIs directly to complete cloud tasks independently.\n"
        "- Agents should NOT ask users to perform manual cloud operations or API calls.\n"
        "- Route tasks based on cloud provider: AWS tasks → AWS Agent, Azure tasks → Azure Agent, GCP tasks → GCP Agent."
    ),
    add_handoff_back_messages=True,
    output_mode="full_history",
).compile(name="cloud_agent").with_config({"recursion_limit": 150})