"""FastAPI application factory with explicit runtime and auth dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from agent_core import AgentRequest, AgentRuntime
from agent_core.conversations import ConversationRepository


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
    message: str
    tool_calls: list[dict[str, object]]


def create_app(
    *,
    runtime: AgentRuntime,
    conversations: ConversationRepository,
    authenticate: Callable[..., AuthenticatedPrincipal],
) -> FastAPI:
    """Create an API with auth and storage adapters supplied by deployment."""

    app = FastAPI(title="DevOps Agent API", version="1")

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

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
        principal: AuthenticatedPrincipal = Depends(authenticate),
    ) -> TurnOutput:
        conversation = await conversations.get(principal.user_id, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        previous = await conversations.list_messages(principal.user_id, conversation_id)
        user_message = await conversations.add_message(
            principal.user_id, conversation_id, "user", body.content
        )
        run_id = uuid4().hex
        result = await runtime.run(
            AgentRequest(
                user_id=principal.user_id,
                conversation_id=conversation_id,
                run_id=run_id,
                message=body.content,
                history=tuple(
                    {"role": item.role, "content": item.content}
                    for item in (*previous, user_message)
                ),
            )
        )
        if result.message:
            await conversations.add_message(
                principal.user_id, conversation_id, "assistant", result.message
            )
        return TurnOutput(
            run_id=run_id,
            message=result.message,
            tool_calls=[
                {"call_id": call.call_id, "name": call.name, "arguments": dict(call.arguments)}
                for call in result.tool_calls
            ],
        )

    return app


__all__ = ["AuthenticatedPrincipal", "create_app"]
