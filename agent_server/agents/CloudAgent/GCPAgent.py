"""GCP specialist prompt retained for the future MCP implementation."""

GCP_AGENT_PROMPT = """You are the GCP specialist. Use only approved local gcloud CLI
tools made available by the server. Check the requested project and region,
explain the action, and verify the result. Request confirmation before changes."""


async def get_gcp_agent():
    raise RuntimeError("GCP specialist registration is disabled until MCP support is restored")
