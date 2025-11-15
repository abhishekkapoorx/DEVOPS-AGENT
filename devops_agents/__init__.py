"""
DevOps Agents Module - Official LangChain DeepAgents Implementation

This module contains the modular implementation using CompiledSubAgent pattern.

**modular** (PRODUCTION-READY): 
- Uses CompiledSubAgent pattern with existing agents
- Wraps agents from /agents directory (BuilderAgent, CloudAgent, etc.)
- Deep agent patterns with reflection and self-critique
- Context quarantine enforced
   - Most robust and maintainable

Subagents:
- builder_expert: Docker + Kubernetes (wraps BuilderAgent)
- cloud_expert: AWS/Azure/GCP (wraps CloudAgent)
- coder_expert: Code & file management (wraps CoderAgent)
- thinker_expert: Strategic planning (wraps ThinkerAgent)
- watcher_expert: Monitoring & observability (wraps WatcherAgent)
"""

# Note: We don't import here to avoid circular imports
# Import directly from submodules instead:
# from devops_agents.modular import invoke_modular_agent

__all__ = [
    "modular",
]

