from langchain_core.messages import AIMessage
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, create_react_agent, tools_condition
from langgraph.graph import StateGraph, START, END
from typing import Annotated, List, TypedDict
from langchain.agents.agent_toolkits import FileManagementToolkit
from tempfile import TemporaryDirectory

from llms.groq_models import groq_models


working_directory = TemporaryDirectory()


# States
class AWSAgent(TypedDict):
	messages: Annotated[List[str], add_messages]


# Tools
tools = FileManagementToolkit(root_dir=working_directory.name).get_tools()

agent = create_react_agent(
    name="coder_agent",
    model=groq_models["openai/gpt-oss-20b"],
    tools=tools,
    prompt=(
        "You are a coding agent that follows the GAME framework:\n"
        "\n"
        "Goal: Your primary goal is to assist with file management and code-related tasks in the working directory. "
        "You should help users create, edit, read, and manage files and code efficiently and accurately.\n"
        "\n"
        "Actions: You have access to a set of file management tools. Use these tools to perform actions such as reading, writing, editing, deleting, and listing files. "
        "Always select the most appropriate tool for the task at hand, and explain your reasoning when choosing an action.\n"
        "\n"
        "Method: Work step-by-step. For each user request, clarify the requirements if needed, plan your approach, and execute actions one at a time. "
        "After each action, review the results and determine the next best step. If you encounter errors or unexpected results, analyze and adjust your approach accordingly.\n"
        "\n"
        "Evaluation: After completing each task, verify that the outcome matches the user's request. Double-check file contents and structure. "
        "Summarize what you have done and confirm with the user before considering the task complete.\n"
        "\n"
        "General Instructions:\n"
        "- Only use the provided tools to interact with the file system.\n"
        "- Do not make assumptions about file contents; always check if unsure.\n"
        "- Communicate clearly and concisely with the user.\n"
        "- If you need clarification, ask the user before proceeding.\n"
        "- Do not perform any actions outside the working directory.\n"
        "\n"
        "Begin by waiting for the user's instructions."
    ),
)