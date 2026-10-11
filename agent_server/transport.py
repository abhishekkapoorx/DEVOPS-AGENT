"""Authenticated HTTP and WebSocket transport for the server agent.

The transport carries intent and results only. Tool execution remains on the
CLI side, which keeps cloud credentials and local command execution out of the
server process.
"""

from __future__ import annotations

import hmac
import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .server_agent import AgentResponse, ServerAgent
from agent_protocol import (
    AgentMessage,
    ErrorMessage,
    TokenRequest,
    ToolRequestMessage,
    ToolResultMessage,
    UserMessage,
)


def _token_is_valid(candidate: str, expected: str | None) -> bool:
    return bool(expected and hmac.compare_digest(candidate, expected))


def _authorization_token(websocket: WebSocket) -> str | None:
    header = websocket.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return websocket.query_params.get("token")


def _results_message(results: list[ToolResultMessage]) -> str:
    return "Tool results:\n" + json.dumps(
        [
            {"request_id": result.request_id, "result": result.result}
            for result in results
        ],
        sort_keys=True,
    )


@dataclass
class TransportSession:
    """State for one authenticated WebSocket conversation."""

    user_id: str
    session_id: str = field(default_factory=lambda: str(uuid4()))
    history: list[Any] = field(default_factory=list)


async def _run_turn(
    websocket: WebSocket,
    agent: Any,
    session: TransportSession,
    message: str,
    max_rounds: int,
) -> None:
    current = message
    for _ in range(max_rounds):
        response: AgentResponse = await agent.arun(
            user_id=session.user_id,
            session_id=session.session_id,
            message=current,
            history=session.history,
        )
        from langchain_core.messages import AIMessage, HumanMessage

        session.history.extend(
            (HumanMessage(content=current), AIMessage(content=response.message))
        )
        if response.message:
            await websocket.send_json(
                AgentMessage(
                    type="agent_message",
                    message=response.message,
                    final=not response.requests,
                ).model_dump()
            )
        if not response.requests:
            return

        request_ids: set[str] = set()
        for request in response.requests:
            request_id = str(uuid4())
            request_ids.add(request_id)
            await websocket.send_json(
                ToolRequestMessage(
                    type="tool_request",
                    request_id=request_id,
                    tool=request.tool,
                    action=request.action,
                    arguments=request.arguments,
                ).model_dump()
            )

        results: list[ToolResultMessage] = []
        while request_ids:
            try:
                incoming = ToolResultMessage.model_validate(await websocket.receive_json())
            except (ValueError, TypeError, ValidationError):
                await websocket.send_json(
                    ErrorMessage(type="error", message="Malformed tool result").model_dump()
                )
                continue
            if incoming.request_id not in request_ids:
                await websocket.send_json(
                    ErrorMessage(type="error", message="Unknown tool request ID").model_dump()
                )
                continue
            request_ids.remove(incoming.request_id)
            results.append(incoming)
        current = _results_message(results)

    await websocket.send_json(
        ErrorMessage(type="error", message="Maximum agent rounds reached").model_dump()
    )


def create_app(
    *,
    agent_factory: Callable[[], Any] | None = None,
    auth_token: str | None = None,
    max_rounds: int = 8,
) -> FastAPI:
    """Create the authenticated API application.

    ``auth_token`` should be supplied by deployment configuration or via
    ``DEVOPS_AGENT_AUTH_TOKEN``. There is deliberately no permissive default.
    """

    if max_rounds < 1:
        raise ValueError("max_rounds must be positive")
    expected_token = auth_token or os.getenv("DEVOPS_AGENT_AUTH_TOKEN")
    app = FastAPI(title="DevOps Agent Transport")
    sessions: dict[tuple[str, str], TransportSession] = {}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/auth/token")
    async def authenticate(request: TokenRequest) -> JSONResponse:
        if not _token_is_valid(request.token, expected_token):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return JSONResponse({"authenticated": True, "token_type": "bearer"})

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        token = _authorization_token(websocket)
        if not _token_is_valid(token or "", expected_token):
            await websocket.close(code=1008, reason="Unauthorized")
            return
        await websocket.accept()
        agent = agent_factory() if agent_factory else ServerAgent()
        session: TransportSession | None = None
        try:
            while True:
                try:
                    incoming = UserMessage.model_validate(await websocket.receive_json())
                except (ValueError, TypeError, ValidationError):
                    await websocket.send_json(
                        ErrorMessage(type="error", message="Malformed message").model_dump()
                    )
                    continue
                if session is None:
                    session_id = incoming.session_id or str(uuid4())
                    session = sessions.setdefault(
                        (incoming.user_id, session_id),
                        TransportSession(user_id=incoming.user_id, session_id=session_id),
                    )
                elif (incoming.user_id, incoming.session_id or session.session_id) != (
                    session.user_id,
                    session.session_id,
                ):
                    await websocket.send_json(
                        ErrorMessage(type="error", message="Session identity mismatch").model_dump()
                    )
                    continue
                await _run_turn(websocket, agent, session, incoming.message, max_rounds)
        except WebSocketDisconnect:
            return

    return app


app = create_app()

__all__ = [
    "AgentMessage", "ErrorMessage", "ToolRequestMessage", "ToolResultMessage",
    "TokenRequest", "TransportSession", "UserMessage", "app", "create_app",
]
