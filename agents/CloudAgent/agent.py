from langgraph_supervisor import create_supervisor
import asyncio
from threading import Thread

from .AWSAgent import get_aws_agent
from .AzureAgent import agent as azure_agent
from .GCPAgent import get_gcp_agent
from llms import DEFAULT_MODEL
from tools.HandOffs.cloud import (
    aws_agent_handoff,
    azure_agent_handoff,
    gcp_agent_handoff
)
from utils.context_middleware import (
    bind_context_before_model,
    bind_context_for_tools,
)
from utils.agent_hooks import build_combined_pre_model_hook

CLOUD_AGENT_PROMPT = """
Developer: You are a Supervisor agent tasked with overseeing and coordinating a set of specialized sub-agents, each responsible for a major cloud platform: AWS, Azure, and GCP. Your role is to efficiently manage these sub-agents to enable autonomous, multi-cloud operations without manual end-user intervention. Below is your operational framework and set of governance rules:

Rules for Supervisor Agent Operation:
- Assign and delegate cloud tasks exclusively to one sub-agent at a time. Avoid parallel assignments or responsibility overlaps among agents.
- Do not directly execute or interfere with any cloud operation; your function is strictly delegation, supervision, and task routing.
- Grant each sub-agent AUTONOMY: Direct them to independently utilize their respective cloud APIs, tools, and services to accomplish assigned tasks.
- Sub-agents must not request manual or direct cloud actions from end-users; all tasks must be autonomously completed by the appropriate sub-agent.
- Ensure strict and explicit task routing:
  * AWS-specific requests → AWS Agent
  * Azure-specific requests → Azure Agent
  * GCP-specific requests → GCP Agent
- All sub-agents follow the THINK-PLAN-ACT-REFLECT operational loop:
  * THINK: Analyze the task requirements, infrastructure needs, and dependencies for the specific cloud platform.
  * PLAN: Prepare a detailed infrastructure plan, select and design needed resources, and assess security, compliance, and cost implications.
  * ACT: Deploy and manage resources directly using cloud provider APIs/tools, actively monitor progress, and resolve issues.
  * REFLECT: Review operational outcomes, verify for issues or misconfigurations, and prompt or enact adjustments for optimization.

Examples:
1. If a user requests to provision an EC2 instance on AWS, route this task exclusively to the AWS Agent.
2. If a request is made for configuring Azure storage, assign the task only to the Azure Agent.
3. For provisioning and monitoring a new GCP Compute Engine VM, the GCP Agent must be given the task exclusively.

Your overarching objective is to orchestrate efficient, secure, and fully automated multi-cloud management with no manual intervention, maximizing operational effectiveness and compliance across all managed platforms.
"""

def _resolve_agent_sync(async_agent):
    try:
        print(f"\n\n\nResolving agent synchronously {async_agent.__name__}\n\n\n")
        return asyncio.run(async_agent())
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                result = {}

                def runner():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    result["agent"] = new_loop.run_until_complete(async_agent())
                    new_loop.close()

                t = Thread(target=runner, daemon=True)
                t.start()
                t.join()
                return result["agent"]
            else:
                return loop.run_until_complete(async_agent())
        except Exception:
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(async_agent())
            finally:
                new_loop.close()

# Resolve the async AWS agent at import time
aws_agent = _resolve_agent_sync(get_aws_agent)
# azure_agent = _resolve_agent_sync(get_azure_agent)
gcp_agent = _resolve_agent_sync(get_gcp_agent)

cloud_pre_model_hook = build_combined_pre_model_hook(
    model=DEFAULT_MODEL,
    rag_retriever=None,
    trim_kwargs={
        "max_messages": 5,
        "summarize_old": True,
    },
    planning_kwargs={
        "min_messages_for_update": 5,
        "max_plan_versions": 3,
    },
)

agent = create_supervisor(
    supervisor_name="cloud_agent",
    model=DEFAULT_MODEL,
    agents=[aws_agent, gcp_agent, azure_agent],
    tools=[
        aws_agent_handoff,
        azure_agent_handoff,
        gcp_agent_handoff
    ],
    prompt=CLOUD_AGENT_PROMPT,
    add_handoff_back_messages=True,
    output_mode="full_history",
    pre_model_hook=cloud_pre_model_hook,
    middleware=[bind_context_before_model, bind_context_for_tools],
).compile(name="cloud_agent").with_config({"recursion_limit": 150})