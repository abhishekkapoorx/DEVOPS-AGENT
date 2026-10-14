"""Authenticated WebSocket client for the cloud agent transport."""

from __future__ import annotations

import json
import asyncio
from typing import Any, Callable

from pydantic import ValidationError
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from .executor import CommandExecutor, ExecutionRequest
from agent_protocol import AgentMessage, ErrorMessage, ToolRequestMessage, redact_secrets


class AgentWebSocketClient:
    """Send user messages and execute the server's requests locally."""

    def __init__(
        self,
        url: str,
        token: str,
        *,
        user_id: str = "cli-user",
        session_id: str | None = None,
        executor: CommandExecutor | None = None,
        max_retries: int = 2,
        retry_delay: float = 0.25,
        receive_timeout: float = 60.0,
        approval_callback=None,
    ):
        if not url.startswith("wss://"):
            raise ValueError("Agent transport requires a wss:// URL")
        if max_retries < 0 or retry_delay < 0 or receive_timeout <= 0:
            raise ValueError("retry values must be non-negative and receive_timeout must be positive")
        self.url = url
        self.token = token
        self.user_id = user_id
        self.session_id = session_id
        self.executor = executor or CommandExecutor(approval_callback=approval_callback, user_id=user_id, session_id=session_id or "remote")
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.receive_timeout = receive_timeout
        self._connection: ClientConnection | None = None

    async def __aenter__(self) -> "AgentWebSocketClient":
        await self._connect_with_retry()
        return self

    async def _connect_with_retry(self) -> None:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                self._connection = await connect(
                    self.url,
                    additional_headers={"Authorization": f"Bearer {self.token}"},
                    open_timeout=10,
                )
                return
            except (OSError, TimeoutError, ConnectionClosed) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay)
        raise ConnectionError("Unable to connect to the agent transport") from last_error

    async def __aexit__(self, *_: Any) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def ask(
        self,
        message: str,
        *,
        on_message: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]:
        if not self._connection:
            raise RuntimeError("AgentWebSocketClient must be used as an async context manager")
        for attempt in range(self.max_retries + 1):
            try:
                return await self._ask_once(message, on_message=on_message)
            except (ConnectionClosed, OSError, TimeoutError) as exc:
                if attempt >= self.max_retries:
                    raise ConnectionError("Agent transport connection failed") from exc
                await self.__aexit__()
                await self._connect_with_retry()
        raise AssertionError("unreachable")

    async def _ask_once(
        self,
        message: str,
        *,
        on_message: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]:
        assert self._connection is not None
        await self._connection.send(json.dumps({
            "type": "user_message",
            "message": message,
            "user_id": self.user_id,
            "session_id": self.session_id,
        }))
        messages: list[dict[str, Any]] = []
        while True:
            incoming = await asyncio.wait_for(
                self._connection.recv(), timeout=self.receive_timeout
            )
            if not isinstance(incoming, str):
                raise ValueError("Expected a text JSON WebSocket message")
            try:
                payload = json.loads(incoming)
                if not isinstance(payload, dict):
                    raise ValueError("Transport message must be a JSON object")
                message_type = payload.get("type")
                if message_type == "tool_request":
                    wire_message = ToolRequestMessage.model_validate(payload)
                elif message_type == "agent_message":
                    wire_message = AgentMessage.model_validate(payload)
                elif message_type == "error":
                    wire_message = ErrorMessage.model_validate(payload)
                else:
                    raise ValueError("Unknown agent transport message type")
            except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as exc:
                raise ValueError("Malformed agent transport message") from exc
            safe_payload = redact_secrets(payload)
            messages.append(safe_payload)
            if on_message is not None:
                on_message(safe_payload)
            if isinstance(wire_message, ToolRequestMessage):
                arguments = wire_message.arguments
                raw_args = arguments.get("args", ())
                fallback_args = [wire_message.action]
                if isinstance(raw_args, str):
                    fallback_args.append(raw_args)
                elif isinstance(raw_args, (list, tuple)):
                    fallback_args.extend(str(value) for value in raw_args)
                try:
                    requested_tool = wire_message.tool
                    executable = requested_tool
                    if requested_tool == "cloud":
                        executable = arguments.get("provider")
                        if executable == "gcp":
                            executable = "gcloud"
                        if executable == "azure":
                            executable = "az"
                        if executable not in {"aws", "az", "gcloud"}:
                            raise ValueError("cloud requests require an aws, azure, gcp, or gcloud provider")
                    elif requested_tool == "kubernetes":
                        executable = "kubectl"
                    elif requested_tool == "files":
                        raise ValueError("file requests are not supported by the local CLI")
                    args = _command_arguments(wire_message.action, arguments, executable)
                    request = ExecutionRequest(
                        tool=executable,
                        args=args,
                        cwd=arguments.get("cwd"),
                    )
                    result = self.executor.execute(request, request_id=wire_message.request_id).to_dict()
                except (TypeError, ValueError, KeyError) as exc:
                    result = {
                        "tool": wire_message.tool,
                        "args": fallback_args,
                        "exit_code": 400,
                        "stdout": "",
                        "stderr": str(exc),
                        "duration_ms": 0.0,
                    }
                await self._connection.send(
                    json.dumps({
                        "type": "tool_result",
                        "request_id": wire_message.request_id,
                        "result": redact_secrets(result),
                    })
                )
            elif isinstance(wire_message, AgentMessage) and wire_message.final:
                return messages
            elif isinstance(wire_message, ErrorMessage):
                return messages


__all__ = ["AgentWebSocketClient"]


def _command_arguments(action: str, arguments: dict[str, Any], tool: str) -> tuple[str, ...]:
    """Translate validated structured arguments into a safe argv tuple."""

    positional = arguments.get("args", ())
    if isinstance(positional, str):
        positional = (positional,)
    if not isinstance(positional, (list, tuple)):
        raise ValueError("args must be a string or a sequence")

    result = [action, *(str(value) for value in positional)]
    ignored = {"args", "cwd"}
    if tool in {"aws", "az", "gcloud"}:
        ignored.add("provider")
    for key, value in arguments.items():
        if key in ignored:
            continue
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                result.append(flag)
        elif isinstance(value, (list, tuple)):
            for item in value:
                result.extend((flag, str(item)))
        else:
            result.extend((flag, str(value)))
    return tuple(result)
