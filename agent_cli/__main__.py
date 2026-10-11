"""Interactive and one-shot command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
from typing import Sequence

from .executor import CommandExecutor, ExecutionRequest, SUPPORTED_TOOLS


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute approved local DevOps tool requests")
    parser.add_argument("--interactive", action="store_true", help="Read requests interactively")
    parser.add_argument("--ask", help="Ask an agent a question")
    parser.add_argument("--remote-url", help="Connect to a remote agent WebSocket")
    parser.add_argument("--token", help="Bearer token for --remote-url")
    parser.add_argument("--user-id", default="cli-user")
    parser.add_argument("--session-id")
    parser.add_argument("--tool", choices=sorted(SUPPORTED_TOOLS))
    parser.add_argument("args", nargs="*", help="Arguments passed to the selected tool")
    return parser


def _print_result(executor: CommandExecutor, request: ExecutionRequest) -> None:
    print(executor.execute(request).to_json())


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
    if args.remote_url:
        if not args.ask or not args.token:
            _parser().error("--remote-url requires both --ask and --token")
        from .websocket_client import AgentWebSocketClient

        async def ask_remote() -> list[dict[str, object]]:
            async with AgentWebSocketClient(
                args.remote_url,
                args.token,
                user_id=args.user_id,
                session_id=args.session_id,
            ) as client:
                return await client.ask(args.ask)

        print(json.dumps(asyncio.run(ask_remote())))
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
