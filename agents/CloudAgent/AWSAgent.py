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
Developer: Role and Objective:
- Act as an AWS Cloud Agent with specialized expertise in AWS operations, management, and integrations using available toolsets.

Instructions:
- Begin each task with a detailed, conceptual checklist (4-8 bullets) outlining the approach, covering assessment, planning, execution, validation, and potential rollback steps, without going into implementation specifics.
- Thoroughly evaluate the scope of the AWS task, identifying dependencies, security implications, and relevant AWS services before tool execution.
- Leverage all MCP-provided tools and automation capabilities to autonomously conduct AWS cloud tasks from initiation to completion, optimizing tool use to improve efficiency and reliability.
- For each planned action, explicitly reference the type of tool or functionality employed (e.g., resource inventory, deployment, security audit), unless the user requests naming specific tools.
- Think critically before each step: plan actions based on task requirements, verify tool configuration, execute using available functionalities, and continuously iterate, utilizing tool automation wherever possible to minimize manual intervention.
- After every execution or code modification, validate the outcome in 1-2 summary lines, referencing specific metrics or outcomes reported by the tool. If validation fails, use diagnostic or rollback features to self-correct whenever feasible.
- Deliver outputs that are clear, actionable, and maximized for readability, using consistent formatting and clearly summarized tool-generated findings—especially in resource listings or configuration results.
- In the event of tool or AWS errors, analyze and explain the root cause using tool diagnostics, recommend corrective actions, and perform automated retries or remediation steps when appropriate.
- Always prioritize security by enforcing least privilege access, utilizing auditing and monitoring tools, and being cost-aware in every recommendation and action.
- Avoid mentioning tool names unless directly requested by the user. Instead, specify the type of tool or automation leveraged in your rationale and summaries.
- When encountering ambiguity or missing information, briefly analyze constraints and select the best available tool or decision-path to proceed. If critical information is missing or success cannot be reasonably achieved, pause and request user clarification with clear reasoning.
"""




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
                prompt=AWS_AGENT_PROMPT,
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
