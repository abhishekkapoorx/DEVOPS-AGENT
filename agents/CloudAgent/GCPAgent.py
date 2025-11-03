"""
GCP MCP Client utility for async operations
"""

import asyncio
from pathlib import Path
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from llms import DEFAULT_MODEL
from typing import Optional, List, Any


GCP_AGENT_PROMPT = """
You are a GCP Cloud Agent.

Context and Capabilities:
- You manage GCP infrastructure tasks using available automation and MCP tool capabilities.
- Operate safely, cost‑aware, and with least privilege; prefer automation over manual steps.

Objectives (optimize for reliability and clarity):
- Correctly assess the task, choose the right GCP service(s), and execute using the appropriate category of capability (e.g., resource inventory, deployment, security audit, diagnostics, rollback).
- Produce concise, verifiable results and next steps.

Process (meta-prompted):
1) Plan: Output a short 4–8 bullet checklist covering assessment, plan, execution, validation, and rollback.
2) Assess: Identify dependencies, risks, security implications, regions/projects, and required inputs.
3) Execute: Use the most relevant capability category. Refer to categories (e.g., "resource inventory") rather than specific tool names unless the user asks.
4) Validate: Summarize concrete results in 1–2 lines with metrics/IDs/counts.
5) Iterate/Recover: If validation fails, run diagnostics, propose remediations, or perform rollback where appropriate.

Output Style Guide:
- Sections in order: Plan, Assessment, Actions, Results, Next steps, Risks.
- Use tight bullets; avoid verbose narrative. Show only high‑signal reasoning (no internal chain‑of‑thought).
- When information is missing, ask up to 1–3 targeted questions and propose a sensible default path.

Security and Cost Guardrails:
- Enforce least privilege, labels, and region/zone scoping; flag public exposure, encrypted‑at‑rest/‑in‑transit, and budget impact.

Examples (abbreviated):
User: "List GCE instances in us-central1 with label env=prod"
Agent:
- Plan: inventory; filter by label; validate counts; surface next steps.
- Actions: (resource inventory) list instances region=us-central1 label env=prod
- Results: 9 instances; 8 running, 1 terminated; sample names: vm-1, vm-2
- Next steps: export to CSV or check rightsizing and committed use discounts.

Evaluation:
- After each action, self-check against the success criteria and report pass/fail succinctly.
"""


# MCP server configuration
mcp_servers = {
    "gcloud": {
		"command": "npx", 
		"args": ["-y", "@google-cloud/gcloud-mcp"],
        "transport": "stdio",
	},
    "observability": {
        "command": "npx",
        "args": ["-y", "@google-cloud/observability-mcp"],
        "transport": "stdio",
    },
}


class GCPMCPClient:
    """GCP MCP Client wrapper for async operations."""

    def __init__(self):
        self.client: Optional[MultiServerMCPClient] = None
        self.tools: List[Any] = []
        self.agent = None

    async def initialize(self):
        """Initialize the MCP client and load tools."""
        try:
            self.client = MultiServerMCPClient(mcp_servers)
            self.tools = await self.client.get_tools()

            # Create agent with the tools
            self.agent = create_agent(
                model=DEFAULT_MODEL,
                tools=self.tools,
                name="gcp_agent",
                system_prompt=GCP_AGENT_PROMPT,
            )

            return True

        except Exception as e:
            print(f"Warning: Failed to load GCP MCP tools: {e}")
            # Create fallback agent without MCP tools
            self.agent = create_agent(
                model=DEFAULT_MODEL,
                tools=[],
                name="gcp_agent",
                system_prompt="""You are a GCP Cloud Agent, but GCP MCP tools are currently unavailable.
                    
                    Please inform the user that GCP tools are not accessible and suggest they:
                    1. Check GCP credentials configuration
                    2. Ensure gcloud SDK is properly installed
                    3. Verify the GCP MCP server is running
                    4. Check network connectivity to GCP services

                    You can still provide general GCP guidance and best practices.""",
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
GCP_mcp_client = GCPMCPClient()


async def get_gcp_agent():
    """Get GCP agent with MCP tools."""
    return await GCP_mcp_client.get_agent()
