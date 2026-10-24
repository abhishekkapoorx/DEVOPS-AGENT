"""Cloud supervisor source retained while its MCP specialists are disabled."""

CLOUD_AGENT_PROMPT = """Route cloud work to its provider specialist when that provider is
enabled. Provider agents are currently disabled until the MCP integration is
implemented again."""


def create_cloud_agent():
    raise RuntimeError("Cloud specialists are disabled until MCP support is restored")
