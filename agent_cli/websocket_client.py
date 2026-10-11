"""Authenticated WebSocket client for the cloud agent transport."""

from __future__ import annotations

import json
import asyncio
from typing import Any

from pydantic import ValidationError
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from .executor import CommandExecutor, ExecutionRequest
from agent_protocol import AgentMessage, ErrorMessage, ToolRequestMessage


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
    ):
        if not url.startswith("wss://"):
            raise ValueError("Agent transport requires a wss:// URL")
        if max_retries < 0 or retry_delay < 0 or receive_timeout <= 0:
            raise ValueError("retry values must be non-negative and receive_timeout must be positive")
        self.url = url
        self.token = token
        self.user_id = user_id
        self.session_id = session_id
        self.executor = executor or CommandExecutor()
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

    async def ask(self, message: str) -> list[dict[str, Any]]:
        if not self._connection:
            raise RuntimeError("AgentWebSocketClient must be used as an async context manager")
        for attempt in range(self.max_retries + 1):
            try:
                return await self._ask_once(message)
            except (ConnectionClosed, OSError, TimeoutError) as exc:
                if attempt >= self.max_retries:
                    raise ConnectionError("Agent transport connection failed") from exc
                await self.__aexit__()
                await self._connect_with_retry()
        raise AssertionError("unreachable")

    async def _ask_once(self, message: str) -> list[dict[str, Any]]:
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
            messages.append(payload)
            if isinstance(wire_message, ToolRequestMessage):
                arguments = wire_message.arguments
                args = arguments.get("args", ())
                if isinstance(args, str):
                    args = (args,)
                try:
                    tool = wire_message.tool
                    if tool == "cloud":
                        tool = arguments.get("provider")
                        if tool not in {"aws", "gcloud"}:
                            raise ValueError("cloud requests require an aws or gcloud provider")
                    elif tool == "kubernetes":
                        tool = "kubectl"
                    elif tool == "files":
                        raise ValueError("file requests are not supported by the local CLI")
                    request = ExecutionRequest(
                        tool=tool,
                        args=(wire_message.action, *args),
                        cwd=arguments.get("cwd"),
                    )
                    result = self.executor.execute(request).to_dict()
                except (TypeError, ValueError, KeyError) as exc:
                    result = {
                        "tool": wire_message.tool,
                        "args": [wire_message.action, *args],
                        "exit_code": 400,
                        "stdout": "",
                        "stderr": str(exc),
                        "duration_ms": 0.0,
                    }
                await self._connection.send(
                    json.dumps({
                        "type": "tool_result",
                        "request_id": wire_message.request_id,
                        "result": result,
                    })
                )
            elif isinstance(wire_message, AgentMessage) and wire_message.final:
                return messages
            elif isinstance(wire_message, ErrorMessage):
                return messages


__all__ = ["AgentWebSocketClient"]
