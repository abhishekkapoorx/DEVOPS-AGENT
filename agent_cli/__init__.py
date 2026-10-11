"""Local execution client for approved DevOps tool requests."""

from .executor import (
    CommandExecutor,
    ExecutionRequest,
    ExecutionResult,
    LocalExecutionClient,
    UnsupportedToolError,
)
__all__ = [
    "CommandExecutor",
    "ExecutionRequest",
    "ExecutionResult",
    "LocalExecutionClient",
    "UnsupportedToolError",
    "AgentWebSocketClient",
]


def __getattr__(name: str):
    if name == "AgentWebSocketClient":
        from .websocket_client import AgentWebSocketClient

        return AgentWebSocketClient
    raise AttributeError(name)
