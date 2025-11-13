"""
Example: Using agent with working directory context.

This demonstrates how to set the working directory context for the agent
before runtime, allowing the agent to operate within a specific directory.
"""

from agent import supervisor
from utils.context import set_working_directory_context, create_context
from utils.pretty_print import pretty_print_messages
from openai import APIConnectionError, RateLimitError
import httpx


def stream_run(messages, context, title):
    """Stream updates for a run with pretty printing."""
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


def example_basic_context():
    """Basic example: Set working directory context and stream output."""

    context = set_working_directory_context("/path/to/your/project")

    stream_run(
        [
            {"role": "user", "content": "List all Python files in the project"},
        ],
        context,
        "Basic Context Example",
    )


def example_full_context():
    """Example with full context including user and session IDs."""

    context = create_context(
        working_directory="/path/to/project",
        project_root="/path/to/project",
        user_id="user123",
        session_id="session456",
    )

    stream_run(
        [
            {
                "role": "user",
                "content": "Analyze the codebase structure",
            }
        ],
        context,
        "Full Context Example",
    )


def example_streaming_with_context():
    """Example already streaming via helper."""

    context = set_working_directory_context("/path/to/project")

    stream_run(
        [
            {
                "role": "user",
                "content": "Create a new module",
            }
        ],
        context,
        "Streaming Example",
    )


def example_environment_variable_context():
    """Example: Use environment variable for working directory."""

    import os
    from pathlib import Path

    working_dir = os.getenv("AGENT_WORKING_DIRECTORY", str(Path.cwd()))
    context = set_working_directory_context(working_dir)

    stream_run(
        [
            {
                "role": "user",
                "content": "What files are in this directory?",
            }
        ],
        context,
        "Environment Variable Context Example",
    )


if __name__ == "__main__":
    """Example: Using agent with dummy_projects directory."""

    from pathlib import Path

    project_root = Path(__file__).parent.parent
    dummy_projects_dir = project_root / "dummy_projects"

    harmonia_path = dummy_projects_dir / "harmonia_flask"
    harmonia_context = set_working_directory_context(str(harmonia_path))

    stream_run(
        [
            {
                "role": "user",
                "content": "List all Python files in this project",
            }
        ],
        harmonia_context,
        "Dummy Project: harmonia_flask",
    )

    justifi_path = dummy_projects_dir / "justi-fi-next"
    justifi_context = set_working_directory_context(str(justifi_path))

    stream_run(
        [
            {
                "role": "user",
                "content": "What TypeScript configuration files are in this project?",
            }
        ],
        justifi_context,
        "Dummy Project: justi-fi-next",
    )

