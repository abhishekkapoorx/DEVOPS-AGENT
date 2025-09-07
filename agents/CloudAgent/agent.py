from langgraph_supervisor import create_supervisor
import asyncio
from threading import Thread

from .AWSAgent import get_aws_agent
from .AzureAgent import agent as azure_agent
from .GCPAgent import agent as gcp_agent
from llms import DEFAULT_MODEL

def _resolve_aws_agent_sync():
    try:
        print("\n\n\nResolving AWS agent synchronously\n\n\n")
        return asyncio.run(get_aws_agent())
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                result = {}

                def runner():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    result["agent"] = new_loop.run_until_complete(get_aws_agent())
                    new_loop.close()

                t = Thread(target=runner, daemon=True)
                t.start()
                t.join()
                return result["agent"]
            else:
                return loop.run_until_complete(get_aws_agent())
        except Exception:
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(get_aws_agent())
            finally:
                new_loop.close()

# Resolve the async AWS agent at import time
aws_agent = _resolve_aws_agent_sync()

agent = create_supervisor(
    supervisor_name="cloud_agent",
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
        "- Route tasks based on cloud provider: AWS tasks → AWS Agent, Azure tasks → Azure Agent, GCP tasks → GCP Agent.\n"
        "- THINK-PLAN-ACT-REFLECT: Instruct agents to:\n"
        "  * THINK: Analyze cloud requirements, understand infrastructure needs, identify dependencies\n"
        "  * PLAN: Create infrastructure plan, identify required resources, consider security and cost implications\n"
        "  * ACT: Execute cloud operations using APIs/tools, monitor deployment, handle errors\n"
        "  * REFLECT: Evaluate deployment success, identify issues, adjust configuration if needed"
    ),
    add_handoff_back_messages=True,
    output_mode="full_history",
).compile(name="cloud_agent").with_config({"recursion_limit": 150})