"""
AWS MCP Client utility for async operations
"""

import asyncio
from pathlib import Path
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from llms import DEFAULT_MODEL
from typing import Optional, List, Any

# Get the current directory for the MCP server path
current_dir = Path(__file__).parent
aws_mcp_server_path = current_dir / "aws_mcp_server.py"

# MCP server configuration
mcp_servers = {
    "awslabs.aws-api-mcp-server": {
        "command": "python",
        "args": ["-m", "awslabs.aws_api_mcp_server.server"],
        "transport": "stdio",
        "env": {"AWS_REGION": "us-east-1"},
        # "disabled": False,
        # "autoApprove": [],
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
            self.tools = await self.client.get_tools()

            # Create ReAct agent with the tools
            self.agent = create_react_agent(
                model=DEFAULT_MODEL,
                tools=self.tools,
                name="aws_agent_mcp",
                prompt="""You are an AWS Cloud Agent specialized in AWS operations and management.
                
                    Instructions:
                    - Use the tools made available to you via MCP to complete cloud tasks end-to-end.
                    - Maintain autonomy: think, plan, act with tools, and iterate without requiring manual user steps.
                    - Provide clear, actionable outputs; format resource listings for readability.
                    - On errors, explain the issue, propose a fix, and retry when appropriate.
                    - Prioritize security, least privilege, and cost awareness in recommendations.
                    - Do not enumerate or name specific tools unless the user asks.

                    When uncertain, briefly analyze and then select the most relevant tool to proceed.""",
            )

            return True

        except Exception as e:
            print(f"Warning: Failed to load AWS MCP tools: {e}")
            # Create fallback agent without MCP tools
            self.agent = create_react_agent(
                model=DEFAULT_MODEL,
                tools=[],
                name="aws_agent_fallback",
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
