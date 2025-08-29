from llms import groq_models
from agents.CloudAgent import agent as CloudAgent
from agents.BuilderAgent import agent as BuilderAgent
from agents.CoderAgent import agent as CoderAgent
from langgraph_supervisor import create_supervisor


supervisor = create_supervisor(
    name="supervisor",
    model=groq_models["openai/gpt-oss-20b"],
    agents=[CloudAgent, BuilderAgent, CoderAgent],
    prompt=(
        "You are a supervisor managing the following agents:\n"
        "- a cloud agent. Assign cloud-related tasks to this agent\n"
        "- a builder agent. Assign builder-related tasks to this agent\n"
        "- a file management agent. Assign file management tasks to this agent\n"
        "Assign work to one agent at a time, do not call agents in parallel.\n"
        "Do not do any work yourself."
    ),
    add_handoff_back_messages=True,
    output_mode="full_history",
).compile(name="supervisor")




