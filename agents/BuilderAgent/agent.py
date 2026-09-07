"""
Builder Agent - DeepAgents Architecture

This agent uses deepagents CompiledSubAgent pattern to coordinate:
- DockerAgent: Containerization tasks
- K8sAgent: Kubernetes orchestration
"""

from deepagents import create_deep_agent, CompiledSubAgent
from deepagents.backends import CompositeBackend, StoreBackend, FilesystemBackend
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.runnables import Runnable
from loguru import logger

from llms import DEFAULT_MODEL
from utils.context_middleware import (
    bind_context_before_model,
    bind_context_for_tools,
)
from .DockerAgent import create_docker_agent
from .K8sAgent import create_k8s_agent


def ensure_sync_runnable(runnable: Runnable) -> Runnable:
    """
    Ensure a runnable supports synchronous invocation for deepagents.
    
    Args:
        runnable: The compiled LangGraph to wrap
        
    Returns:
        Runnable that supports synchronous invocation
    """
    class SyncRunnableWrapper(Runnable):
        """Wrapper to ensure synchronous invocation"""
        def __init__(self, wrapped):
            super().__init__()
            self.wrapped = wrapped
            # Copy attributes that might be needed
            for attr in ['name', 'graph', 'nodes', 'edges']:
                if hasattr(wrapped, attr):
                    setattr(self, attr, getattr(wrapped, attr))
        
        def invoke(self, input, config=None, **kwargs):
            """Synchronous invoke - delegates to wrapped runnable"""
            return self.wrapped.invoke(input, config, **kwargs)
        
        def ainvoke(self, input, config=None, **kwargs):
            """Async invoke - delegates to wrapped runnable"""
            return self.wrapped.ainvoke(input, config, **kwargs)
        
        def stream(self, input, config=None, **kwargs):
            """Stream - delegates to wrapped runnable"""
            return self.wrapped.stream(input, config, **kwargs)
        
        def astream(self, input, config=None, **kwargs):
            """Async stream - delegates to wrapped runnable"""
            return self.wrapped.astream(input, config, **kwargs)
    
    return SyncRunnableWrapper(runnable)


BUILDER_AGENT_PROMPT = """You are a Builder Agent Supervisor responsible for orchestrating containerization and orchestration tasks.

You manage specialized subagents:
- docker_expert: Containerization and Docker-related tasks (Dockerfiles, docker-compose, optimization)
- k8s_expert: Kubernetes orchestration (manifests, Helm charts, cluster management)

Delegate tasks to the appropriate subagent:
- Docker/containerization requests → docker_expert
- Kubernetes/orchestration requests → k8s_expert
- Hybrid requests → start with docker_expert, then k8s_expert

Use the task() tool to delegate work to subagents. This keeps context clean and improves results."""


def create_builder_agent():
    """
    Create Builder Agent using deepagents architecture.
    
    Returns:
        Compiled deep agent ready for invocation
    """
    logger.info("Creating Builder Agent with deepagents architecture...")
    
    # Create sub-agents (they're already compiled StateGraphs)
    docker_agent_graph = create_docker_agent().compile(name="docker_agent").with_config({"recursion_limit": 150})
    k8s_agent_graph = create_k8s_agent().compile(name="k8s_agent").with_config({"recursion_limit": 150})
    
    # Wrap to ensure sync support
    docker_agent_runnable = ensure_sync_runnable(docker_agent_graph)
    k8s_agent_runnable = ensure_sync_runnable(k8s_agent_graph)
    
    # Create CompiledSubAgents
    docker_subagent = CompiledSubAgent(
        name="docker_expert",
        description="Docker containerization expert. Use for creating Dockerfiles, docker-compose files, container optimization, and Docker best practices. Includes codebase analysis and quality assurance.",
        runnable=docker_agent_runnable
    )
    
    k8s_subagent = CompiledSubAgent(
        name="k8s_expert",
        description="Kubernetes orchestration expert. Use for creating K8s manifests, Helm charts, ingress configuration, monitoring setup, and cluster management. Includes reflection and validation.",
        runnable=k8s_agent_runnable
    )
    
    # Create backend factory (uses current working directory by default)
    def create_backend(runtime):
        """Create composite backend for file operations."""
        import os
        root_dir = os.path.abspath(os.getcwd())
        fs_backend = FilesystemBackend(root_dir=root_dir)
        return CompositeBackend(
            default=fs_backend,
            routes={
                "/memories/": StoreBackend(runtime),
            }
        )
    
    # Create checkpointer and store
    checkpointer = MemorySaver()
    store = InMemoryStore()
    
    # Create the deep agent
    agent = create_deep_agent(
        model=DEFAULT_MODEL,
        system_prompt=BUILDER_AGENT_PROMPT,
        tools=[],  # Builder agent delegates to subagents
        subagents=[
            docker_subagent,
            k8s_subagent,
        ],
        backend=create_backend,
        checkpointer=checkpointer,
        store=store,
    )
    
    logger.info("✅ Builder Agent created with deepagents architecture!")
    logger.info("Subagents:")
    logger.info("  - docker_expert (Docker containerization)")
    logger.info("  - k8s_expert (Kubernetes orchestration)")
    
    return agent


# Create the agent instance
agent = create_builder_agent()
