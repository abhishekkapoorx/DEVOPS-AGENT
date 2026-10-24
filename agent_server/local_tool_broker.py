"""Authenticated request bridge from server runs to user-side tool helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from agent_core.tools import ToolExecutionContext, ToolResult
from agent_protocol import (
    PLATFORMS,
    available_local_tool_definitions,
    validate_local_tool_arguments,
)


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
        self._connected_users: dict[str, tuple[str, str]] = {}
        self._helper_ready: dict[str, asyncio.Event] = {}

    def connect_helper(self, user_id: str, platform: str, workspace: str) -> bool:
        if platform not in PLATFORMS or not workspace or len(workspace) > 4_096:
            return False
        path_type = PureWindowsPath if platform == "windows" else PurePosixPath
        if not path_type(workspace).is_absolute():
            return False
        if user_id in self._connected_users:
            return False
        self._connected_users[user_id] = (platform, workspace)
        self._helper_ready.setdefault(user_id, asyncio.Event()).set()
        return True

    def disconnect_helper(self, user_id: str) -> None:
        self._connected_users.pop(user_id, None)
        self._helper_ready.setdefault(user_id, asyncio.Event()).clear()
        for (pending_user, _call_id), pending in tuple(self._pending.items()):
            if pending_user == user_id and not pending.result.done():
                pending.result.set_result({
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "Local helper disconnected before responding",
                    "duration_ms": 0,
                })

    async def stream_calls(self, user_id: str):
        """Yield queued calls and `None` keepalives for one helper connection."""
        try:
            while True:
                try:
                    yield await asyncio.wait_for(self.next_call(user_id), timeout=15)
                except TimeoutError:
                    yield None
        finally:
            self.disconnect_helper(user_id)

    async def list_tools(self, *, context: ToolExecutionContext):
        if context.user_id not in self._connected_users:
            ready = self._helper_ready.setdefault(context.user_id, asyncio.Event())
            try:
                await asyncio.wait_for(ready.wait(), timeout=10)
            except TimeoutError:
                pass
        helper = self._connected_users.get(context.user_id)
        platform, workspace = helper if helper is not None else (None, None)
        platform = platform or "other"
        tools = []
        for definition in available_local_tool_definitions(platform):
            if definition.name.endswith(".command"):
                description = (
                    f"Run an approved {definition.tool} command in the user's local workspace. "
                    "Pass arguments as an argv list; never use shell syntax."
                )
            elif definition.name == "files.list_files":
                description = (
                    f"List entries in an absolute directory path under the local workspace {workspace}."
                    if workspace else "List entries in an absolute directory path inside the user's local workspace."
                )
            elif definition.name == "files.grep":
                description = "Search the full local workspace recursively using GNU grep basic regular expressions."
            else:
                description = (
                    "Search the local workspace recursively using ripgrep regular expressions. "
                    "By default ripgrep follows ignore rules and skips hidden and binary files."
                )
            tools.append(definition.as_tool_definition(description))
        return tuple(tools)

    async def execute(
        self, *, name: str, version: str, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> ToolResult:
        platform = (self._connected_users.get(context.user_id) or ("other", ""))[0]
        try:
            _definition, tool_arguments = validate_local_tool_arguments(
                name, arguments, platform=platform, version=version
            )
        except (TypeError, ValueError) as exc:
            return ToolResult(context.call_id, name, "rejected", error=str(exc))

        loop = asyncio.get_running_loop()
        pending = PendingCall(
            context.user_id,
            {"run_id": context.run_id, "call_id": context.call_id, "name": name,
             "version": version, "arguments": tool_arguments},
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
