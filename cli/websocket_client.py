"""Authenticated WebSocket client for the cloud agent transport."""

from __future__ import annotations

import json
from typing import Any

from websockets.asyncio.client import ClientConnection, connect

from .executor import CommandExecutor, ExecutionRequest


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
    ):
        self.url = url
        self.token = token
        self.user_id = user_id
        self.session_id = session_id
        self.executor = executor or CommandExecutor()
        self._connection: ClientConnection | None = None

    async def __aenter__(self) -> "AgentWebSocketClient":
        self._connection = await connect(
            self.url,
            additional_headers={"Authorization": f"Bearer {self.token}"},
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def ask(self, message: str) -> list[dict[str, Any]]:
        if not self._connection:
            raise RuntimeError("AgentWebSocketClient must be used as an async context manager")
        await self._connection.send(json.dumps({
            "type": "user_message",
            "message": message,
            "user_id": self.user_id,
            "session_id": self.session_id,
        }))
        messages: list[dict[str, Any]] = []
        while True:
            incoming = await self._connection.recv()
            if not isinstance(incoming, str):
                raise ValueError("Expected a text JSON WebSocket message")
            payload = json.loads(incoming)
            messages.append(payload)
            if payload.get("type") == "tool_request":
                arguments = payload.get("arguments", {})
                args = arguments.get("args", ())
                if isinstance(args, str):
                    args = (args,)
                request = ExecutionRequest(
                    tool=payload["tool"],
                    args=(payload["action"], *args),
                    cwd=arguments.get("cwd"),
                )
                result = self.executor.execute(request)
                await self._connection.send(
                    json.dumps({
                        "type": "tool_result",
                        "request_id": payload["request_id"],
                        "result": result.to_dict(),
                    })
                )
            elif payload.get("type") == "agent_message" and payload.get("final"):
                return messages
            elif payload.get("type") == "error":
                return messages


__all__ = ["AgentWebSocketClient"]
