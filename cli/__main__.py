"""Interactive and one-shot command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys
from typing import Sequence

from .executor import CommandExecutor, ExecutionRequest, SUPPORTED_TOOLS


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute approved local DevOps tool requests")
    parser.add_argument("--interactive", action="store_true", help="Read requests interactively")
    parser.add_argument("--ask", help="Ask the server agent an infrastructure question")
    parser.add_argument("--user-id", default="cli-user")
    parser.add_argument("--session-id", default="cli-session")
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
        args = (raw_args,) if tool == "shell" else tuple(shlex.split(raw_args))
        try:
            _print_result(executor, ExecutionRequest(tool=tool, args=args))
        except (ValueError, OSError) as exc:
            print(json.dumps({"error": str(exc)}))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.ask:
        from agent_loop import ExecutionLoop, ToolExecution
        from server_agent import ServerAgent

        def progress(execution: ToolExecution) -> None:
            print(
                f"[{execution.request.tool}:{execution.request.action}] "
                f"exit={execution.result.exit_code}",
                file=sys.stderr,
            )

        response = asyncio.run(
            ExecutionLoop(agent=ServerAgent(), progress=progress).run(
                user_id=args.user_id,
                session_id=args.session_id,
                message=args.ask,
            )
        )
        print(json.dumps({"message": response.message, "rounds": response.rounds}))
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
