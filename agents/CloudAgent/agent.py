
from langgraph_supervisor import create_supervisor

from .AWSAgent import agent as aws_agent
from .AzureAgent import agent as azure_agent
from .GCPAgent import agent as gcp_agent
from llms.groq_models import groq_models

supervisor = create_supervisor(
    name="cloud_agent",
    model=groq_models["openai/gpt-oss-20b"],
    agents=[aws_agent, azure_agent, gcp_agent],
    prompt=(
        "You are a supervisor managing the following agents:\n"
        "- a cloud agent. Assign cloud-related tasks to this agent\n"
        "Assign work to one agent at a time, do not call agents in parallel.\n"
        "Do not do any work yourself."
    ),
    add_handoff_back_messages=True,
    output_mode="full_history",
).compile(name="cloud_agent")