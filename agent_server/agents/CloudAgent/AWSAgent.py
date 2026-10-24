"""AWS specialist prompt retained for the future MCP implementation."""

AWS_AGENT_PROMPT = """You are the AWS specialist. Use only approved local AWS CLI tools
made available by the server. Check the requested account and region, explain
the action, and verify the result. Request confirmation before changes."""


async def get_aws_agent():
    raise RuntimeError("AWS specialist registration is disabled until MCP support is restored")
