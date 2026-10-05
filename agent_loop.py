"""End-to-end orchestration between the server agent and local executors.

The loop is deliberately independent of HTTP and WebSocket transports. Those
transports can call :meth:`ExecutionLoop.run` and stream the returned progress
events without needing to know anything about LangGraph internals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

from cli import CommandExecutor, ExecutionRequest, ExecutionResult, UnsupportedToolError
from langchain_core.messages import AIMessage, HumanMessage
from server_agent import AgentResponse, ToolRequest


class AgentRunner(Protocol):
    async def arun(
        self,
        *,
        user_id: str,
        session_id: str,
        message: str,
        history: Sequence[Any] | None = None,
    ) -> AgentResponse: ...


Policy = Callable[..., bool]
Progress = Callable[[Any], None]


@dataclass(frozen=True)
class ToolExecution:
    """One requested operation and the result returned to the agent."""

    request: ToolRequest
    result: ExecutionResult


@dataclass(frozen=True)
class LoopResponse:
    """Final answer plus all local executions performed for this user turn."""

    message: str
    executions: tuple[ToolExecution, ...] = ()
    rounds: int = 1


@dataclass
class ConversationState:
    """Conversation state retained between agent rounds in one session."""

    messages: list[Any] = field(default_factory=list)


def _arguments(request: ToolRequest) -> tuple[str, ...]:
    """Convert structured arguments to CLI arguments without shell parsing."""

    values = request.arguments.get("args", ())
    if isinstance(values, str):
        values = (values,)
    if not isinstance(values, (list, tuple)):
        raise ValueError("arguments.args must be a string or list")
    return (request.action, *(str(value) for value in values))


def execution_request_for(request: ToolRequest) -> ExecutionRequest:
    """Map a server request to the local client's strict tool contract."""

    tool = request.tool
    if tool == "cloud":
        provider = request.arguments.get("provider")
        if provider not in {"aws", "gcloud"}:
            raise UnsupportedToolError("cloud requests require provider aws or gcloud")
        tool = provider
    elif tool == "kubernetes":
        tool = "kubectl"
    elif tool not in {"docker", "git", "shell"}:
        raise UnsupportedToolError(f"No local executor is registered for {request.tool!r}")

    args = _arguments(request)
    if tool == "shell":
        args = (request.arguments.get("command", request.action),)
    return ExecutionRequest(tool=tool, args=args, cwd=request.arguments.get("cwd"))


def _error_result(request: ToolRequest, message: str, exit_code: int) -> ExecutionResult:
    return ExecutionResult(
        tool=request.tool,
        args=(request.action,),
        exit_code=exit_code,
        stdout="",
        stderr=message,
        duration_ms=0.0,
    )


def _result_message(executions: Sequence[ToolExecution]) -> str:
    payload = [
        {
            "request": execution.request.model_dump(),
            "result": execution.result.to_dict(),
        }
        for execution in executions
    ]
    return (
        "Tool execution results. Use these results to answer the user or decide "
        "the next operation.\n" + json.dumps(payload, sort_keys=True)
    )


class ExecutionLoop:
    """Run structured requests locally and continue the agent with their results."""

    def __init__(
        self,
        *,
        agent: AgentRunner,
        executor: CommandExecutor | None = None,
        policy: Policy | None = None,
        max_rounds: int = 8,
        progress: Progress | None = None,
    ) -> None:
        if max_rounds < 1:
            raise ValueError("max_rounds must be positive")
        self.agent = agent
        self.executor = executor or CommandExecutor()
        self.policy = policy or (lambda request, **context: True)
        self.max_rounds = max_rounds
        self.progress = progress
        self._sessions: dict[tuple[str, str], ConversationState] = {}

    async def run(
        self,
        *,
        user_id: str,
        session_id: str,
        message: str,
        state: ConversationState | None = None,
    ) -> LoopResponse:
        if not message.strip():
            raise ValueError("message must not be empty")
        state = state or self._sessions.setdefault((user_id, session_id), ConversationState())
        current_message = message
        all_executions: list[ToolExecution] = []

        for round_number in range(1, self.max_rounds + 1):
            response = await self.agent.arun(
                user_id=user_id,
                session_id=session_id,
                message=current_message,
                history=state.messages,
            )
            state.messages.extend(
                (HumanMessage(content=current_message), AIMessage(content=response.message))
            )
            if not response.requests:
                return LoopResponse(response.message, tuple(all_executions), round_number)

            executions: list[ToolExecution] = []
            for request in response.requests:
                try:
                    executable = execution_request_for(request)
                    approved = self.policy(
                        executable, user_id=user_id, session_id=session_id
                    )
                    if not approved:
                        result = _error_result(request, "Execution requires approval", 403)
                    else:
                        result = self.executor.execute(executable)
                except (PermissionError, TypeError, ValueError, UnsupportedToolError) as exc:
                    result = _error_result(request, str(exc), 400)
                executions.append(ToolExecution(request=request, result=result))

            all_executions.extend(executions)
            if self.progress:
                for execution in executions:
                    self.progress(execution)
            current_message = _result_message(executions)

        return LoopResponse(
            "The agent reached the maximum number of execution rounds.",
            tuple(all_executions),
            self.max_rounds,
        )


__all__ = [
    "ConversationState",
    "ExecutionLoop",
    "LoopResponse",
    "ToolExecution",
    "execution_request_for",
]
