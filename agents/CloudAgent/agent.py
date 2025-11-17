"""
Cloud Agent - DeepAgents Architecture

This agent uses deepagents CompiledSubAgent pattern to coordinate:
- AWSAgent: AWS cloud operations
- AzureAgent: Azure cloud operations
- GCPAgent: GCP cloud operations
"""

from deepagents import create_deep_agent, CompiledSubAgent
from deepagents.backends import CompositeBackend, StoreBackend, FilesystemBackend
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.runnables import Runnable
from loguru import logger
import asyncio
from threading import Thread

from llms import DEFAULT_MODEL
from utils.context_middleware import (
    bind_context_before_model,
    bind_context_for_tools,
)
from .AWSAgent import get_aws_agent
from .AzureAgent import agent as azure_agent
from .GCPAgent import get_gcp_agent


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


def _resolve_agent_sync(async_agent):
    """Resolve async agent to sync runnable."""
    try:
        logger.debug(f"Resolving agent synchronously {async_agent.__name__}")
        return asyncio.run(async_agent())
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                result = {}

                def runner():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    result["agent"] = new_loop.run_until_complete(async_agent())
                    new_loop.close()

                t = Thread(target=runner, daemon=True)
                t.start()
                t.join()
                return result["agent"]
            else:
                return loop.run_until_complete(async_agent())
        except Exception:
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(async_agent())
            finally:
                new_loop.close()


CLOUD_AGENT_PROMPT = """You are a Supervisor agent tasked with overseeing and coordinating specialized sub-agents, each responsible for a major cloud platform: AWS, Azure, and GCP.

Your role is to efficiently manage these sub-agents to enable autonomous, multi-cloud operations without manual end-user intervention.

Rules for Supervisor Agent Operation:
- Assign and delegate cloud tasks exclusively to one sub-agent at a time. Avoid parallel assignments or responsibility overlaps among agents.
- Do not directly execute or interfere with any cloud operation; your function is strictly delegation, supervision, and task routing.
- Grant each sub-agent AUTONOMY: Direct them to independently utilize their respective cloud APIs, tools, and services to accomplish assigned tasks.
- Sub-agents must not request manual or direct cloud actions from end-users; all tasks must be autonomously completed by the appropriate sub-agent.
- Ensure strict and explicit task routing:
  * AWS-specific requests → aws_expert
  * Azure-specific requests → azure_expert
  * GCP-specific requests → gcp_expert

Use the task() tool to delegate work to subagents. This keeps context clean and improves results.

Your overarching objective is to orchestrate efficient, secure, and fully automated multi-cloud management with no manual intervention, maximizing operational effectiveness and compliance across all managed platforms."""


def create_cloud_agent():
    """
    Create Cloud Agent using deepagents architecture.
    
    Returns:
        Compiled deep agent ready for invocation
    """
    logger.info("Creating Cloud Agent with deepagents architecture...")
    
    # Resolve async agents to sync runnables
    try:
        aws_agent_graph = _resolve_agent_sync(get_aws_agent)
    except Exception as e:
        logger.warning(f"Failed to load AWS agent: {e}")
        aws_agent_graph = None
    
    try:
        gcp_agent_graph = _resolve_agent_sync(get_gcp_agent)
    except Exception as e:
        logger.warning(f"Failed to load GCP agent: {e}")
        gcp_agent_graph = None
    
    # Azure agent is already sync
    azure_agent_graph = azure_agent
    
    # Wrap to ensure sync support
    subagents = []
    
    if aws_agent_graph:
        aws_agent_runnable = ensure_sync_runnable(aws_agent_graph)
        aws_subagent = CompiledSubAgent(
            name="aws_expert",
            description="AWS cloud infrastructure expert. Use for AWS resource provisioning, architecture design, cost estimation, and AWS best practices. Operates autonomously using AWS APIs.",
            runnable=aws_agent_runnable
        )
        subagents.append(aws_subagent)
    
    if gcp_agent_graph:
        gcp_agent_runnable = ensure_sync_runnable(gcp_agent_graph)
        gcp_subagent = CompiledSubAgent(
            name="gcp_expert",
            description="Google Cloud Platform expert. Use for GCP resource provisioning, architecture design, cost estimation, and GCP best practices. Operates autonomously using GCP APIs.",
            runnable=gcp_agent_runnable
        )
        subagents.append(gcp_subagent)
    
    # Azure agent
    azure_agent_runnable = ensure_sync_runnable(azure_agent_graph)
    azure_subagent = CompiledSubAgent(
        name="azure_expert",
        description="Microsoft Azure cloud infrastructure expert. Use for Azure resource provisioning, architecture design, cost estimation, and Azure best practices. Currently in development.",
        runnable=azure_agent_runnable
    )
    subagents.append(azure_subagent)
    
    # Create backend factory
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
        system_prompt=CLOUD_AGENT_PROMPT,
        tools=[],  # Cloud agent delegates to subagents
        subagents=subagents,
        backend=create_backend,
        checkpointer=checkpointer,
        store=store,
    )
    
    logger.info("✅ Cloud Agent created with deepagents architecture!")
    logger.info("Subagents:")
    if aws_agent_graph:
        logger.info("  - aws_expert (AWS cloud operations)")
    if gcp_agent_graph:
        logger.info("  - gcp_expert (GCP cloud operations)")
    logger.info("  - azure_expert (Azure cloud operations)")
    
    return agent


# Create the agent instance
agent = create_cloud_agent()
