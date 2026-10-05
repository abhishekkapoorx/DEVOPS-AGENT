"""Application entry point for the server-side DevOps agent."""

from server_agent import AgentResponse, ServerAgent, SessionContext, ToolRequest, run_agent


def _build_graph() -> ServerAgent:
    """Build the request-producing agent used by application integrations."""

    return ServerAgent()


# Kept as the configured graph name for existing LangGraph integrations. It
# does not import or expose local execution tools.
supervisor = _build_graph()

__all__ = [
    "AgentResponse",
    "ServerAgent",
    "SessionContext",
    "ToolRequest",
    "run_agent",
    "supervisor",
]
