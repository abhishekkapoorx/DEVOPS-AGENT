"""Framework-independent contracts for the DevOps Agent backend."""

from .runtime import AgentRequest, AgentResponse, AgentRuntime, AgentToolCall
from .conversations import Conversation, ConversationMessage, ConversationRepository
from .tools import RegisteredTool, ToolDefinition, ToolExecutionContext, ToolResult

__all__ = [
    "AgentRequest",
    "AgentResponse",
    "AgentRuntime",
    "AgentToolCall",
    "Conversation",
    "ConversationMessage",
    "ConversationRepository",
    "RegisteredTool",
    "ToolDefinition",
    "ToolExecutionContext",
    "ToolResult",
]
