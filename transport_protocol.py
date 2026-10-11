"""Shared, dependency-light schemas for the agent transport wire protocol."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TokenRequest(Message):
    token: str = Field(min_length=1)


class UserMessage(Message):
    type: Literal["user_message"]
    message: str = Field(min_length=1)
    user_id: str = Field(default="cli-user", min_length=1)
    session_id: str | None = Field(default=None, min_length=1)


class AgentMessage(Message):
    type: Literal["agent_message"]
    message: str
    final: bool = True


class ToolRequestMessage(Message):
    type: Literal["tool_request"]
    request_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    action: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResultMessage(Message):
    type: Literal["tool_result"]
    request_id: str = Field(min_length=1)
    result: dict[str, Any]


class ErrorMessage(Message):
    type: Literal["error"]
    message: str


__all__ = [
    "AgentMessage",
    "ErrorMessage",
    "Message",
    "TokenRequest",
    "ToolRequestMessage",
    "ToolResultMessage",
    "UserMessage",
]
