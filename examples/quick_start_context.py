"""
Quick Start: Using agent with dummy_projects context.

This is a simple example showing how to set the working directory context
to one of your test projects in dummy_projects.
"""

from agent import supervisor
from utils.context import set_working_directory_context, get_dummy_projects_path
from utils.pretty_print import pretty_print_messages
from openai import APIConnectionError, RateLimitError
import httpx


def stream_and_print(messages, context, title):
    """Stream agent execution with pretty printed updates."""
    print("=" * 60)
    print(title)
    print("=" * 60)
    print()

    try:
        for update in supervisor.stream(
            {"messages": messages},
            context=context,
            stream_mode="updates",
        ):
            pretty_print_messages(update, last_message=False)
    except (APIConnectionError, httpx.ConnectError) as exc:
        print("Connection error while calling the model:", exc)
        print(
            "Check your network connection and OpenAI credentials "
            "(OPENAI_API_KEY / endpoint) before retrying."
        )
    except RateLimitError as exc:
        print("Rate limit error:", exc)
        print(
            "The request exceeded token limits. This may be due to:\n"
            "1. RAG context being too large\n"
            "2. Conversation history being too long\n"
            "3. Rate limits on your OpenAI account\n\n"
            "Try reducing the query complexity or wait before retrying."
        )

    print("\n")


def work_with_harmonia_flask():
    """Example: Work with the harmonia_flask project."""
    
    # Get the path to harmonia_flask
    dummy_projects = get_dummy_projects_path()
    harmonia_path = dummy_projects / "harmonia_flask"
    
    # Set the working directory context
    context = set_working_directory_context(str(harmonia_path))
    
    # Invoke the agent - it will operate in the harmonia_flask directory
    stream_and_print(
        [
            {
                "role": "user",
                "content": "Analyze the Flask application structure and list all API routes",
            }
        ],
        context,
        "harmonia_flask run",
    )


def work_with_justifi_next():
    """Example: Work with the justi-fi-next project."""
    
    dummy_projects = get_dummy_projects_path()
    justifi_path = dummy_projects / "justi-fi-next"
    
    context = set_working_directory_context(str(justifi_path))
    
    stream_and_print(
        [
            {
                "role": "user",
                "content": "What are the main components in this Next.js application?",
            }
        ],
        context,
        "justi-fi-next run",
    )


if __name__ == "__main__":
    print("Quick Start: Agent with Context")
    print("=" * 60)
    print()
    
    # Example: Work with harmonia_flask
    print("Working with harmonia_flask project...")
    work_with_harmonia_flask()
    print("=" * 60 + "\n")
    
    # Example: Work with justi-fi-next
    print("Working with justi-fi-next project...")
    work_with_justifi_next()

