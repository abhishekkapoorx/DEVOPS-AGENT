"""Framework-independent contracts for the DevOps Agent backend."""

from .runtime import AgentRequest, AgentResponse, AgentRuntime, AgentToolCall
from .runs import AgentRun, IdempotencyConflict, RunEvent, RunLeaseLost, RunRepository, RunState
from .conversations import Conversation, ConversationMessage, ConversationRepository
from .tools import RegisteredTool, ToolDefinition, ToolExecutionContext, ToolResult

__all__ = [
    "AgentRequest",
    "AgentResponse",
    "AgentRuntime",
    "AgentToolCall",
    "AgentRun",
    "IdempotencyConflict",
    "RunEvent",
    "RunLeaseLost",
    "RunRepository",
    "RunState",
    "Conversation",
    "ConversationMessage",
    "ConversationRepository",
    "RegisteredTool",
    "ToolDefinition",
    "ToolExecutionContext",
    "ToolResult",
]
