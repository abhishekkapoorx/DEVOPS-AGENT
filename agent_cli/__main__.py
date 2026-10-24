"""Interactive and one-shot command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import subprocess
from typing import Any, Sequence

from .executor import LocalToolExecutor, SUPPORTED_TOOLS


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
    parser.add_argument("--tui", action="store_true", help="Open the Textual conversation interface")
    parser.add_argument("--tool", choices=sorted(SUPPORTED_TOOLS))
    parser.add_argument("args", nargs="*", help="Arguments passed to the selected tool")
    return parser


def _print_result(executor: LocalToolExecutor, name: str, arguments: dict[str, Any]) -> None:
    print(executor.execute(name, arguments).to_json())


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


def _start_local_helper(api_url: str, *, approval_ipc: bool = False) -> subprocess.Popen:
    command = [sys.executable, "-m", "agent_cli.tool_service", "--api-url", api_url]
    if approval_ipc:
        command.append("--approval-ipc")
    return subprocess.Popen(
        command,
        cwd=os.getcwd(),
        stdin=subprocess.PIPE if approval_ipc else None,
        stdout=subprocess.PIPE if approval_ipc else None,
        text=approval_ipc,
        bufsize=1 if approval_ipc else -1,
    )


def _stop_local_helper(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def interactive(executor: LocalToolExecutor | None = None) -> None:
    executor = executor or LocalToolExecutor(approval_callback=_approve_local_request)
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
            name, arguments = _cli_tool_call(tool, args)
            _print_result(executor, name, arguments)
        except (ValueError, OSError) as exc:
            print(json.dumps({"error": str(exc)}))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.auth or args.ask or args.tui or (not args.interactive and args.tool is None):
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
        if args.tui or (not args.ask and not args.interactive and args.tool is None):
            from .rest_client import RestAgentClient
            from .textual_app import run_textual_app

            def client_factory(initial_tokens):
                token_holder = [initial_tokens]

                def access_token() -> str:
                    return token_holder[0].access_token

                def refresh_access_token() -> str | None:
                    refreshed = auth.restore()
                    if refreshed is None:
                        return None
                    token_holder[0] = refreshed
                    return refreshed.access_token

                return RestAgentClient(
                    args.api_url,
                    access_token=access_token,
                    refresh_access_token=refresh_access_token,
                )

            helper = []
            def start_helper(_tokens):
                if not helper:
                    helper.append(_start_local_helper(args.api_url, approval_ipc=True))
                return helper[0]
            try:
                run_textual_app(auth, client_factory, on_signed_in=start_helper)
            finally:
                _stop_local_helper(helper[0] if helper else None)
            return 0
    if args.ask:
        tokens = auth.restore()
        if tokens is None:
            from .auth_ui import run_auth_ui

            tokens = run_auth_ui(auth)
            if tokens is None:
                return 0
        from .rest_client import RestAgentClient

        client = RestAgentClient(
            args.api_url,
            access_token=lambda: tokens.access_token,
            refresh_access_token=lambda: (
                (refreshed.access_token if (refreshed := auth.restore()) else None)
            ),
        )
        helper = _start_local_helper(args.api_url)
        try:
            result = client.ask(
                args.ask,
                conversation_id=args.session_id,
                on_event=_print_progress,
            )
        finally:
            _stop_local_helper(helper)
        print(result.get("message", ""))
        return 0
    if args.interactive:
        interactive()
        return 0
    if args.tool is None:
        _parser().error("provide --interactive or --tool")
    name, arguments = _cli_tool_call(args.tool, tuple(args.args))
    _print_result(LocalToolExecutor(approval_callback=_approve_local_request), name, arguments)
    return 0


def _cli_tool_call(tool: str, args: tuple[str, ...]) -> tuple[str, dict[str, Any]]:
    if tool != "files":
        return f"{tool}.command", {"argv": list(args)}
    if not args:
        raise ValueError("files requires an action")
    action, *values = args
    if action in {"list", "list_files"} and len(values) == 1:
        return "files.list_files", {"path": values[0]}
    if action in {"grep", "ripgrep"} and len(values) == 1:
        return f"files.{action}", {"pattern": values[0]}
    raise ValueError("files supports list <absolute-path>, grep <regex>, or ripgrep <regex>")


def _approve_local_request(name: str, arguments: dict[str, Any], _operation) -> bool:
    print(f"Tool request: {name} {json.dumps(arguments, sort_keys=True)}")
    try:
        return input("Allow this command? [y/N] ").strip().lower() in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
