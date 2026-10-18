"""FastAPI application factory with explicit runtime and auth dependencies."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_core import AgentRuntime
from agent_core.conversations import ConversationRepository
from agent_core.runs import IdempotencyConflict, RunRepository, RunState
from agent_server.auth_sessions import AuthSessionService
from agent_server.run_worker import AgentRunWorker
from .auth_routes import create_auth_router
from .security import require_authenticated_user


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: str


class CreateConversation(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=200)


class ConversationMessageInput(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)


class ConversationOutput(BaseModel):
    id: str
    title: str


class MessageOutput(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class TurnOutput(BaseModel):
    run_id: str
    message_id: str
    status: RunState
    message: str
    tool_calls: list[dict[str, object]]


class RunOutput(TurnOutput):
    error: str | None = None


class RunEventOutput(BaseModel):
    sequence: int
    type: str
    data: dict[str, object]
    created_at: str


def create_app(
    *,
    runtime: AgentRuntime,
    conversations: ConversationRepository,
    runs: RunRepository,
    auth_service: AuthSessionService,
    run_worker: AgentRunWorker | None = None,
) -> FastAPI:
    """Create an API with auth and storage adapters supplied by deployment."""

    worker = run_worker or AgentRunWorker(
        runtime=runtime, conversations=conversations, runs=runs
    )

    @asynccontextmanager
    async def lifespan(_app):
        stopping = asyncio.Event()
        worker_task = asyncio.create_task(worker.run_forever(stopping))
        try:
            yield
        finally:
            stopping.set()
            await worker_task

    app = FastAPI(title="DevOps Agent API", version="1", lifespan=lifespan)
    app.include_router(create_auth_router(auth_service))

    def authenticate(
        authorization: str | None = Header(default=None),
    ) -> AuthenticatedPrincipal:
        user = require_authenticated_user(authorization, auth_service)
        return AuthenticatedPrincipal(user_id=user.user_id)

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        if not await conversations.health_check():
            raise HTTPException(status_code=503, detail="Persistence is unavailable")
        return {"status": "ready"}

    @app.post(
        "/v1/conversations",
        response_model=ConversationOutput,
        status_code=status.HTTP_201_CREATED,
        tags=["conversations"],
    )
    async def create_conversation(
        body: CreateConversation,
        principal: AuthenticatedPrincipal = Depends(authenticate),
    ) -> ConversationOutput:
        conversation = await conversations.create(principal.user_id, body.title)
        return ConversationOutput(id=conversation.id, title=conversation.title)

    @app.get(
        "/v1/conversations",
        response_model=list[ConversationOutput],
        tags=["conversations"],
    )
    async def list_conversations(
        principal: AuthenticatedPrincipal = Depends(authenticate),
    ) -> list[ConversationOutput]:
        values = await conversations.list_for_user(principal.user_id)
        return [ConversationOutput(id=item.id, title=item.title) for item in values]

    @app.get(
        "/v1/conversations/{conversation_id}/messages",
        response_model=list[MessageOutput],
        tags=["conversations"],
    )
    async def list_messages(
        conversation_id: str,
        principal: AuthenticatedPrincipal = Depends(authenticate),
    ) -> list[MessageOutput]:
        if await conversations.get(principal.user_id, conversation_id) is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        messages = await conversations.list_messages(principal.user_id, conversation_id)
        return [
            MessageOutput(
                id=item.id,
                role=item.role,
                content=item.content,
                created_at=item.created_at.isoformat(),
            )
            for item in messages
        ]

    @app.post(
        "/v1/conversations/{conversation_id}/messages",
        response_model=TurnOutput,
        tags=["conversations"],
    )
    async def send_message(
        conversation_id: str,
        body: ConversationMessageInput,
        background_tasks: BackgroundTasks,
        response: Response,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=255),
        principal: AuthenticatedPrincipal = Depends(authenticate),
    ) -> TurnOutput:
        conversation = await conversations.get(principal.user_id, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        request_hash = hashlib.sha256(body.content.encode("utf-8")).hexdigest()
        try:
            run, is_new = await runs.create_or_get_run(
                principal.user_id,
                conversation_id,
                idempotency_key,
                request_hash,
                body.content,
            )
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="Conversation not found") from exc

        if not is_new:
            if run.state in {"pending", "running", "waiting_for_approval"}:
                response.status_code = status.HTTP_202_ACCEPTED
                background_tasks.add_task(worker.run_once)
            return _run_output(run)

        response.status_code = status.HTTP_202_ACCEPTED
        background_tasks.add_task(worker.run_once)
        return _run_output(run)

    @app.get("/v1/runs/{run_id}", response_model=RunOutput, tags=["runs"])
    async def get_run(
        run_id: str,
        principal: AuthenticatedPrincipal = Depends(authenticate),
    ) -> RunOutput:
        run = await runs.get_run(principal.user_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return _run_output(run)

    @app.get("/v1/runs/{run_id}/events", response_model=list[RunEventOutput], tags=["runs"])
    async def list_run_events(
        run_id: str,
        after: int = Query(default=0, ge=0),
        principal: AuthenticatedPrincipal = Depends(authenticate),
    ) -> list[RunEventOutput]:
        if await runs.get_run(principal.user_id, run_id) is None:
            raise HTTPException(status_code=404, detail="Run not found")
        events = await runs.list_run_events(principal.user_id, run_id, after)
        return [
            RunEventOutput(
                sequence=event.sequence,
                type=event.event_type,
                data=dict(event.data),
                created_at=event.created_at.isoformat(),
            )
            for event in events
        ]

    @app.get("/v1/runs/{run_id}/events/stream", tags=["runs"])
    async def stream_run_events(
        run_id: str,
        after: int = Query(default=0, ge=0),
        principal: AuthenticatedPrincipal = Depends(authenticate),
    ) -> StreamingResponse:
        if await runs.get_run(principal.user_id, run_id) is None:
            raise HTTPException(status_code=404, detail="Run not found")

        async def events():
            sequence = after
            terminal_states = {"completed", "failed", "cancelled", "expired"}
            while True:
                current = await runs.get_run(principal.user_id, run_id)
                if current is None:
                    return
                pending = await runs.list_run_events(principal.user_id, run_id, sequence)
                for event in pending:
                    sequence = event.sequence
                    data = {**dict(event.data), "created_at": event.created_at.isoformat()}
                    yield (
                        f"id: {event.sequence}\n"
                        f"event: {event.event_type}\n"
                        f"data: {json.dumps(data, separators=(',', ':'))}\n\n"
                    )
                if current.state in terminal_states and not pending:
                    return
                if not pending:
                    yield ": keep-alive\n\n"
                    await asyncio.sleep(1)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _run_output(run) -> RunOutput:
    return RunOutput(
        run_id=run.id,
        message_id=run.message_id,
        status=run.state,
        message=run.message,
        tool_calls=[dict(call) for call in run.tool_calls],
        error=run.error,
    )


__all__ = ["AuthenticatedPrincipal", "create_app"]
