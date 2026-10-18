"""Interactive and one-shot command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from typing import Any, Sequence

from .executor import CommandExecutor, ExecutionRequest, SUPPORTED_TOOLS


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute approved local DevOps tool requests")
    parser.add_argument("--interactive", action="store_true", help="Read requests interactively")
    parser.add_argument("--ask", help="Ask an agent a question")
    parser.add_argument(
        "--api-url",
        default=os.environ.get("DEVOPS_AGENT_API_URL"),
        help="Backend REST API base URL (or DEVOPS_AGENT_API_URL)",
    )
    parser.add_argument("--session-id", help="Resume this conversation ID")
    parser.add_argument("--auth", action="store_true", help="Open the Textual authentication screen")
    parser.add_argument("--tool", choices=sorted(SUPPORTED_TOOLS))
    parser.add_argument("args", nargs="*", help="Arguments passed to the selected tool")
    return parser


def _print_result(executor: CommandExecutor, request: ExecutionRequest) -> None:
    print(executor.execute(request).to_json())


def _print_progress(message: dict[str, Any]) -> None:
    """Show redacted transport progress without corrupting the final JSON output."""

    message_type = message.get("type")
    if message_type == "agent_message":
        print(message.get("message", ""), file=sys.stderr, flush=True)
    elif message_type == "tool_request":
        print(
            f"Executing {message.get('tool', 'tool')}.{message.get('action', 'operation')}...",
            file=sys.stderr,
            flush=True,
        )
    elif message_type == "run_event":
        print(f"Agent run: {message.get('type', 'event')}", file=sys.stderr, flush=True)
    elif message_type == "error":
        print(f"Agent error: {message.get('message', 'unknown error')}", file=sys.stderr, flush=True)


def interactive(executor: CommandExecutor | None = None) -> None:
    executor = executor or CommandExecutor()
    print("Enter a tool name, or 'quit' to exit.")
    while True:
        tool = input("tool> ").strip()
        if tool in {"quit", "exit", ""}:
            return
        if tool not in SUPPORTED_TOOLS:
            print(f"Unsupported tool: {tool}")
            continue
        raw_args = input("args> ")
        args = tuple(shlex.split(raw_args))
        try:
            _print_result(executor, ExecutionRequest(tool=tool, args=args))
        except (ValueError, OSError) as exc:
            print(json.dumps({"error": str(exc)}))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.auth or args.ask:
        if not args.api_url:
            _parser().error("authentication and agent requests require --api-url or DEVOPS_AGENT_API_URL")
        from .auth import DeviceLogin, RestAuthApi, SystemCredentialStore

        def show_verification(url: str, code: str) -> None:
            print(f"Open {url} and enter code {code}", file=sys.stderr, flush=True)

        auth = DeviceLogin(
            api=RestAuthApi(args.api_url),
            credentials=SystemCredentialStore(),
            verification_callback=show_verification,
        )
        if args.auth:
            from .auth_ui import run_auth_ui

            result = run_auth_ui(auth)
            if result is not None:
                print(f"Signed in as {result.user_id}")
            return 0
    if args.ask:
        tokens = auth.restore()
        if tokens is None:
            from .auth_ui import run_auth_ui

            tokens = run_auth_ui(auth)
            if tokens is None:
                return 0
        token_holder = [tokens]

        def access_token() -> str:
            return token_holder[0].access_token

        def refresh_access_token() -> str | None:
            refreshed = auth.restore()
            if refreshed is None:
                return None
            token_holder[0] = refreshed
            return refreshed.access_token

        from .rest_client import RestAgentClient

        client = RestAgentClient(
            args.api_url,
            access_token=access_token,
            refresh_access_token=refresh_access_token,
        )
        result = client.ask(
            args.ask,
            conversation_id=args.session_id,
            on_event=_print_progress,
        )
        print(result.get("message", ""))
        return 0
    if args.interactive:
        interactive()
        return 0
    if args.tool is None:
        _parser().error("provide --interactive or --tool")
    _print_result(CommandExecutor(), ExecutionRequest(tool=args.tool, args=tuple(args.args)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
