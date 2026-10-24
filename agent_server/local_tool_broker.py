"""Authenticated request bridge from server runs to user-side tool helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from agent_core.tools import ToolExecutionContext, ToolResult


TOOLS = ("aws", "az", "gcloud", "kubectl", "docker", "git", "files")


@dataclass
class PendingCall:
    user_id: str
    payload: dict[str, Any]
    result: asyncio.Future[dict[str, Any]]


class LocalToolBroker:
    """Hold pending calls until the authenticated user's local helper replies."""

    def __init__(self, timeout: float = 300) -> None:
        self.timeout = timeout
        self._queues: dict[str, asyncio.Queue[PendingCall]] = {}
        self._pending: dict[tuple[str, str], PendingCall] = {}
        self._connected_users: set[str] = set()

    def connect_helper(self, user_id: str) -> bool:
        if user_id in self._connected_users:
            return False
        self._connected_users.add(user_id)
        return True

    def disconnect_helper(self, user_id: str) -> None:
        self._connected_users.discard(user_id)

    async def list_tools(self, *, context: ToolExecutionContext):
        return tuple(
            {
                "name": f"{tool}.command",
                "version": "1.0.0",
                "description": f"Run an approved {tool} command in the user's local workspace. Pass arguments as an argv list; never use shell syntax.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "argv": {"type": "array", "items": {"type": "string"}},
                        "cwd": {"type": "string"},
                    },
                    "required": ["argv"],
                    "additionalProperties": False,
                },
                "required_scopes": [],
                "risk_class": "write",
            }
            for tool in TOOLS
        )

    async def execute(
        self, *, name: str, version: str, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> ToolResult:
        tool = name.partition(".")[0]
        if tool not in TOOLS or version != "1.0.0":
            return ToolResult(context.call_id, name, "rejected", error="Unsupported local tool")
        args = arguments.get("argv")
        cwd = arguments.get("cwd")
        if not isinstance(args, list) or not args or any(not isinstance(arg, str) for arg in args):
            return ToolResult(context.call_id, name, "rejected", error="Tool args must be a non-empty string list")
        if len(args) > 256 or sum(len(arg.encode("utf-8")) for arg in args) > 64_000:
            return ToolResult(context.call_id, name, "rejected", error="Tool arguments exceed the size limit")
        if cwd is not None and not isinstance(cwd, str):
            return ToolResult(context.call_id, name, "rejected", error="cwd must be a path string")

        loop = asyncio.get_running_loop()
        pending = PendingCall(
            context.user_id,
            {"run_id": context.run_id, "call_id": context.call_id, "name": name,
             "version": version, "arguments": {"argv": args, "cwd": cwd}},
            loop.create_future(),
        )
        key = (context.user_id, context.call_id)
        if key in self._pending:
            return ToolResult(context.call_id, name, "rejected", error="Duplicate pending tool call")
        self._pending[key] = pending
        await self._queues.setdefault(context.user_id, asyncio.Queue()).put(pending)
        try:
            response = await asyncio.wait_for(pending.result, timeout=self.timeout)
        except TimeoutError:
            return ToolResult(context.call_id, name, "failed", error="Local helper did not respond in time")
        finally:
            self._pending.pop(key, None)
        status = "succeeded" if response.get("exit_code") == 0 else "failed"
        return ToolResult(
            context.call_id, name, status,
            output={key: response.get(key) for key in ("exit_code", "stdout", "stderr", "duration_ms")},
            error=None if status == "succeeded" else str(response.get("stderr") or "Tool command failed"),
        )

    async def next_call(self, user_id: str) -> dict[str, Any]:
        queue = self._queues.setdefault(user_id, asyncio.Queue())
        while True:
            pending = await queue.get()
            key = (user_id, str(pending.payload["call_id"]))
            if self._pending.get(key) is pending and not pending.result.done():
                return pending.payload

    def submit_result(self, user_id: str, call_id: str, result: dict[str, Any]) -> bool:
        pending = self._pending.get((user_id, call_id))
        if pending is None or pending.result.done():
            return False
        pending.result.set_result(result)
        return True
