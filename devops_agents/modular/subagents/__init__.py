"""
Modular Subagents - Wrappers around existing agents

This module exposes the existing agents from /agents directory
as subagents for the DeepAgents modular implementation.

All agents include:
- Deep agent patterns with reflection
- Self-critique and quality assurance
- Error recovery mechanisms
- Context management
"""

from .builder_subagent import create_builder_subagent
from .cloud_subagent import create_cloud_subagent
from .coder_subagent import create_coder_subagent
from .thinker_subagent import create_thinker_subagent
from .watcher_subagent import create_watcher_subagent

__all__ = [
    "create_builder_subagent",
    "create_cloud_subagent",
    "create_coder_subagent",
    "create_thinker_subagent",
    "create_watcher_subagent",
]
