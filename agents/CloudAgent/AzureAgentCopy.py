"""
Azure MCP Client utility for async operations (Azure Agent)
"""

import os
import asyncio
from pathlib import Path
from typing import Optional, List, Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from llms import DEFAULT_MODEL

# Get the current directory for potential local server module/layout
current_dir = Path(__file__).parent
azure_mcp_server_path = current_dir / "azure_mcp_server.py"

# Allow configuring an Azure MCP Server HTTP endpoint via env
AZURE_MCP_SERVER_URL = os.getenv("AZURE_MCP_SERVER_URL")

# MCP server configuration for Azure
# Prefer HTTP (streamable_http) if provided, else use our local comprehensive server.
mcp_servers = {}

if AZURE_MCP_SERVER_URL:
	mcp_servers["azure-comprehensive-server"] = {
		"url": AZURE_MCP_SERVER_URL,
		"transport": "streamable_http",
	}
else:
	# Use our comprehensive local Azure MCP server
	mcp_servers["azure-comprehensive-server"] = {
		"command": "python",
		"args": [str(azure_mcp_server_path)],
		"transport": "stdio",
		"env": {
			"AZURE_SUBSCRIPTION_ID": os.getenv("AZURE_SUBSCRIPTION_ID", ""),
			"AZURE_TENANT_ID": os.getenv("AZURE_TENANT_ID", ""),
			"AZURE_CLIENT_ID": os.getenv("AZURE_CLIENT_ID", ""),
			"AZURE_CLIENT_SECRET": os.getenv("AZURE_CLIENT_SECRET", ""),
		},
	}


class AzureMCPClient:
	"""Azure MCP Client wrapper for async operations."""

	def __init__(self):
		self.client: Optional[MultiServerMCPClient] = None
		self.tools: List[Any] = []
		self.agent = None

	async def initialize(self) -> bool:
		"""Initialize the MCP client and load tools."""
		try:
			self.client = MultiServerMCPClient(mcp_servers)
			self.tools = await self.client.get_tools()

			# Create ReAct agent with the tools
			self.agent = create_react_agent(
				model=DEFAULT_MODEL,
				tools=self.tools,
				name="azure_agent_mcp",
				prompt=(
					"You are an Azure Cloud Agent specialized in Azure operations and management.\n\n"
					"Instructions:\n"
					"- Use the tools made available to you via MCP to complete Azure tasks end-to-end.\n"
					"- Maintain autonomy: think, plan, act with tools, and iterate without requiring manual user steps.\n"
					"- Provide clear, actionable outputs; format resource listings for readability.\n"
					"- On errors, explain the issue, propose a fix, and retry when appropriate.\n"
					"- Prioritize security, least privilege, and cost awareness in recommendations.\n"
					"- Do not enumerate or name specific tools unless the user asks.\n\n"
					"Available Azure Tools:\n"
					"• Resource Groups: create, list, delete resource groups\n"
					"• Virtual Machines: list VMs with details (size, state, location)\n"
					"• Storage Accounts: list storage accounts with SKU and kind info\n"
					"• AKS Clusters: list Kubernetes clusters with version and node count\n"
					"• Health Check: verify server connectivity and credentials\n\n"
					"Common parameters: subscription_id, resource_group_name, location (defaults to eastus).\n"
					"Authentication via DefaultAzureCredential or service principal (env vars).\n"
				),
			)

			return True

		except Exception as e:
			print(f"Warning: Failed to load Azure MCP tools: {e}")
			# Create fallback agent without MCP tools
			self.agent = create_react_agent(
				model=DEFAULT_MODEL,
				tools=[],
				name="azure_agent_fallback",
				prompt=(
					"You are an Azure Cloud Agent, but Azure MCP tools are currently unavailable.\n\n"
					"Please inform the user that Azure tools are not accessible and suggest they:\n"
					"1. Configure AZURE_MCP_SERVER_URL to a reachable Azure MCP Server endpoint, or\n"
					"2. Ensure a local Azure MCP server module is installed and runnable (e.g., 'azure.mcp.server'), and\n"
					"3. Verify network connectivity and Azure authentication (CLI or Managed Identity).\n\n"
					"You can still provide general Azure guidance and best practices."
				),
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
azure_mcp_client = AzureMCPClient()


async def get_azure_agent():
	"""Get Azure agent with MCP tools."""
	return await azure_mcp_client.get_agent()

# For compatibility with the rest of the codebase, expose `agent` as the compiled agent
# Note: this mirrors the AWS pattern of providing an async getter; some supervisors
# may import `agent` directly. We compile synchronously by scheduling initialization.

# Provide a lightweight placeholder that prompts initialization when first used.
agent = None  # type: ignore

async def ensure_compiled_agent():
	global agent
	if agent is None:
		agent = await get_azure_agent()
	return agent