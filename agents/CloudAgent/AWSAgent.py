"""
AWS MCP Client utility for async operations
"""

import asyncio
from pathlib import Path
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from llms import DEFAULT_MODEL
from typing import Optional, List, Any



AWS_AGENT_PROMPT = """
You are an AWS Cloud Agent.

Context and Capabilities:
- You manage AWS infrastructure tasks using available automation and MCP tool capabilities.
- Operate safely, cost‑aware, and with least privilege; prefer automation over manual steps.

Objectives (optimize for reliability and clarity):
- Correctly assess the task, choose the right AWS service(s), and execute using the appropriate category of capability (e.g., resource inventory, deployment, security audit, diagnostics, rollback).
- Produce concise, verifiable results and next steps.

Process (meta-prompted):
1) Plan: Output a short 4–8 bullet checklist covering assessment, plan, execution, validation, and rollback.
2) Assess: Identify dependencies, risks, security implications, regions, and required inputs.
3) Execute: Use the most relevant capability category. Refer to categories (e.g., "resource inventory") rather than specific tool names unless the user asks.
4) Validate: Summarize concrete results in 1–2 lines with metrics/IDs/counts.
5) Iterate/Recover: If validation fails, run diagnostics, propose remediations, or perform rollback where appropriate.

Output Style Guide:
- Sections in order: Plan, Assessment, Actions, Results, Next steps, Risks.
- Use tight bullets; avoid verbose narrative. Show only high‑signal reasoning (no internal chain‑of‑thought).
- When information is missing, ask up to 1–3 targeted questions and propose a sensible default path.

Security and Cost Guardrails:
- Enforce least privilege, tagging, and region scoping; flag public exposure, encrypted‑at‑rest/‑in‑transit, and budget impact.

Examples (abbreviated):
User: "List EC2 instances in us-east-1 tagged env=prod"
Agent:
- Plan: inventory; filter by tag; validate counts; surface next steps.
- Actions: (resource inventory) list instances region=us-east-1 tag=env:prod
- Results: 12 instances; 11 running, 1 stopped; sample IDs: i-abc..., i-def...
- Next steps: export to CSV or check cost and rightsizing.

Evaluation:
- After each action, self-check against the success criteria and report pass/fail succinctly.
"""


# MCP server configuration
mcp_servers = {
    "awslabs.aws-api-mcp-server": {
        "command": "python",
        "args": ["-m", "awslabs.aws_api_mcp_server.server"],
        "transport": "stdio",
        "env": {"AWS_REGION": "us-east-1"},
    },
    "aws-knowledge-mcp-server": {
        "url":"https://knowledge-mcp.global.api.aws",
        "transport": "streamable_http",
    },
}


class AWSMCPClient:
    """AWS MCP Client wrapper for async operations."""

    def __init__(self):
        self.client: Optional[MultiServerMCPClient] = None
        self.tools: List[Any] = []
        self.agent = None

    async def initialize(self):
        """Initialize the MCP client and load tools."""
        try:
            self.client = MultiServerMCPClient(mcp_servers)
            raw_tools = await self.client.get_tools()

            # Sanitize tool schemas to satisfy LLM tool parameter requirements
            self.tools = []
            for tool in raw_tools:
                try:
                    # Expecting OpenAI-style tool schema: {"type":"function","function":{name, description, parameters}}
                    if isinstance(tool, dict) and tool.get("type") == "function":
                        fn = tool.get("function", {}) or {}
                        params = fn.get("parameters")
                        if not isinstance(params, dict) or not params.get("type"):
                            # Provide a minimal valid JSON schema for parameters
                            fn["parameters"] = {"type": "object", "properties": {}}
                            tool["function"] = fn
                    self.tools.append(tool)
                except Exception:
                    # If anything goes wrong, fall back to the original tool entry
                    self.tools.append(tool)

            # Create ReAct agent with the tools
            self.agent = create_react_agent(
                model=DEFAULT_MODEL,
                tools=self.tools,
                name="aws_agent",
                prompt=AWS_AGENT_PROMPT,
            )

            return True

        except Exception as e:
            print(f"Warning: Failed to load AWS MCP tools: {e}")
            # Create fallback agent without MCP tools
            self.agent = create_react_agent(
                model=DEFAULT_MODEL,
                tools=[],
                name="aws_agent",
                prompt="""You are an AWS Cloud Agent, but AWS MCP tools are currently unavailable. 
                
                    Please inform the user that AWS tools are not accessible and suggest they:
                    1. Check AWS credentials configuration
                    2. Ensure boto3 is properly installed
                    3. Verify the AWS MCP server is running
                    4. Check network connectivity to AWS services

                    You can still provide general AWS guidance and best practices.""",
            )
            return False

    async def get_agent(self):
        """Get the initialized agent."""
        if not self.agent:
            await self.initialize()
        return self.agent

    async def close(self):
        """Close the MCP client."""
        if self.client:
            await self.client.aclose()


# Global instance
aws_mcp_client = AWSMCPClient()


async def get_aws_agent():
    """Get AWS agent with MCP tools."""
    return await aws_mcp_client.get_agent()