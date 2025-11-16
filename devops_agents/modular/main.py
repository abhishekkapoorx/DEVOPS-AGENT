"""
DevOps Agent - Official DeepAgents with CompiledSubAgent Pattern

This implementation follows deepagents best practices:
- Uses CompiledSubAgent for all subagents
- Modular subagent design
- Concise output format
- Context quarantine
- Proper separation of concerns
"""

from deepagents import create_deep_agent, CompiledSubAgent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend, FilesystemBackend
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.runnables import Runnable

from llms import DEFAULT_MODEL
from tools.TerminalTool import shell_tool
from .subagents import (
    create_builder_subagent,
    create_cloud_subagent,
    create_coder_subagent,
    create_thinker_subagent,
    create_watcher_subagent,
)
from loguru import logger
import os


def ensure_sync_runnable(runnable: Runnable) -> Runnable:
    """
    Ensure a runnable supports synchronous invocation for deepagents.
    
    deepagents requires subagents to have a synchronous invoke method.
    This wrapper ensures the runnable can be called synchronously.
    
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


# Main supervisor system prompt
# Per deepagents best practices: concise, use-case specific
# Default deepagents prompt already includes tool usage instructions
DEVOPS_SUPERVISOR_PROMPT = """You are a DevOps Automation Supervisor coordinating specialized subagents to solve complex DevOps tasks.

Your role is to:
- Plan complex tasks using write_todos
- Delegate specialized work to subagents for context isolation
- Coordinate results and provide clear summaries

Available subagents:
- builder_expert: Containerization and orchestration (Docker, Kubernetes)
- cloud_expert: Cloud infrastructure (AWS, Azure, GCP)
- coder_expert: Code generation, refactoring, file management
- thinker_expert: Strategic planning, risk assessment, decision-making
- watcher_expert: Monitoring, observability, performance tracking

For complex tasks, delegate to subagents using the task() tool. This keeps your context clean and improves results."""


def create_backend_factory(root_dir=None):
    """
    Create a backend factory function that uses the provided root directory.
    
    Args:
        root_dir: Optional root directory for file operations. 
                 If None, uses current working directory.
    
    Returns:
        Function that creates CompositeBackend with FilesystemBackend
    """
    import os
    
    # Use provided root_dir or default to current working directory
    if root_dir is None:
        root_dir = os.path.abspath(os.getcwd())
    else:
        root_dir = os.path.abspath(root_dir)
    
    def create_backend(runtime):
        """
        Create composite backend following deepagents best practices.
        
        Per LangChain docs:
        - Default: FilesystemBackend for actual filesystem access (root_dir)
        - /memories/: StoreBackend for persistent cross-thread storage
        """
        # FilesystemBackend with root_dir for all file operations
        fs_backend = FilesystemBackend(root_dir=root_dir)
        
        logger.debug(f"Created FilesystemBackend with root_dir={root_dir}")
        
        # Per deepagents best practices: CompositeBackend
        # Default uses FilesystemBackend for actual file access
        # /memories/ routes to StoreBackend for persistence across threads
        return CompositeBackend(
            default=fs_backend,  # All file operations use FilesystemBackend with root_dir
            routes={
                "/memories/": StoreBackend(runtime),  # Persistent storage across threads
            }
        )
    
    return create_backend


def create_modular_agent(root_dir=None):
    """
    Create the modular DevOps deep agent with CompiledSubAgent pattern.
    
    Args:
        root_dir: Optional root directory for file operations.
                 If None, uses current working directory.
                 This is the base directory for all file system tools (ls, read_file, etc.)
    
    Returns:
        Compiled deep agent ready for invocation
    """
    import os
    
    # Use provided root_dir or default to current working directory
    if root_dir is None:
        root_dir = os.path.abspath(os.getcwd())
    else:
        root_dir = os.path.abspath(root_dir)
    
    logger.info(f"Creating modular compiled subagents from existing agents (root_dir={root_dir})...")

    # Create compiled subagents using existing agents
    # Wrap each agent to ensure synchronous invocation support for deepagents
    builder_subagent = CompiledSubAgent(
        name="builder_expert",
        description="Builder expert for containerization and orchestration. Manages Docker and Kubernetes tasks. Use for creating Dockerfiles, docker-compose files, K8s manifests, and Helm charts. Includes reflection and quality assurance.",
        runnable=create_builder_subagent()
    )

    cloud_subagent = CompiledSubAgent(
        name="cloud_expert",
        description="Cloud infrastructure expert for AWS, Azure, and GCP. Use for architecture design, resource provisioning planning, cost estimation, and cloud best practices. Manages multiple cloud platforms autonomously.",
        runnable=create_cloud_subagent()
    )

    coder_subagent = CompiledSubAgent(
        name="coder_expert",
        description="Code and file management expert. Use for creating, reading, updating files, code generation, refactoring, and code quality assurance. Includes self-reflection and validation mechanisms.",
        runnable=create_coder_subagent()
    )

    thinker_subagent = CompiledSubAgent(
        name="thinker_expert",
        description="Strategic planning and analysis expert. Use for high-level planning, risk assessment, evaluating alternatives, and defining success criteria. Provides deep strategic thinking and decision rationale.",
        runnable=create_thinker_subagent()
    )

    watcher_subagent = CompiledSubAgent(
        name="watcher_expert",
        description="Monitoring and observability expert. Use for tracking system health, performance metrics, anomaly detection, and alert generation. Provides continuous monitoring and recommendations.",
        runnable=create_watcher_subagent()
    )

    # Create the main deep agent
    checkpointer = MemorySaver()
    store = InMemoryStore()

    logger.info("Creating modular DevOps Deep Agent with CompiledSubAgents...")

    # Create backend factory with root_dir
    backend_factory = create_backend_factory(root_dir=root_dir)
    
    agent = create_deep_agent(
        model=DEFAULT_MODEL,
        system_prompt=DEVOPS_SUPERVISOR_PROMPT,
        tools=[shell_tool],  # Additional top-level tools
        subagents=[
            builder_subagent,
            cloud_subagent,
            coder_subagent,
            thinker_subagent,
            watcher_subagent,
        ],
        backend=backend_factory,
        checkpointer=checkpointer,
        store=store,
    )

    logger.info("✅ Modular DevOps Deep Agent created successfully!")
    logger.info("Features:")
    logger.info("  - Built-in planning (write_todos)")
    logger.info("  - File system (ls, read_file, write_file, edit_file)")
    logger.info("  - Subagent delegation (task)")
    logger.info("  - Memory persistence (checkpointer + store)")
    logger.info("  - Deep agent patterns with reflection")
    logger.info("Subagents (CompiledSubAgent pattern):")
    logger.info("  - builder_expert (Docker + Kubernetes)")
    logger.info("  - cloud_expert (AWS/Azure/GCP)")
    logger.info("  - coder_expert (code & file management)")
    logger.info("  - thinker_expert (strategic planning)")
    logger.info("  - watcher_expert (monitoring & observability)")
    logger.info("  - general-purpose (automatic)")
    
    return agent


# Store agents by root_dir (support multiple project roots)
_agents = {}


def get_agent(root_dir=None):
    """
    Get or create the agent instance for a specific root directory.
    
    Args:
        root_dir: Optional root directory. If None, uses current working directory.
                 Different root directories get different agent instances.
    
    Returns:
        Agent instance for the specified root directory
    """
    import os
    
    # Normalize root_dir for use as cache key
    if root_dir is None:
        cache_key = os.path.abspath(os.getcwd())
    else:
        cache_key = os.path.abspath(root_dir)
    
    if cache_key not in _agents:
        _agents[cache_key] = create_modular_agent(root_dir=root_dir)
    
    return _agents[cache_key]


async def invoke_modular_agent_async(message: str, thread_id: str = "default", root_dir: str = None, stream: bool = False):
    """
    Invoke the modular DevOps deep agent asynchronously.
    
    Args:
        message: User's request
        thread_id: Thread ID for conversation persistence
        root_dir: Optional root directory for file operations.
                 If None, uses current working directory.
                 This determines where file system tools (ls, read_file, etc.) operate.
        stream: If True, stream outputs showing tool calls, subagent calls, and AI messages
        
    Returns:
        Agent response with messages, todos, etc.
    """
    from loguru import logger
    from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
    
    agent = get_agent(root_dir=root_dir)
    
    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }
    
    if stream:
        # Stream the execution to show tool calls, subagent calls, and messages
        logger.info("📡 Streaming agent execution (async)...\n")
        
        final_result = None
        async for chunk in agent.astream({
            "messages": [{"role": "user", "content": message}]
        }, config=config):
            # Process each chunk - handle different chunk types
            if not isinstance(chunk, dict):
                # Skip non-dict chunks (like Overwrite objects)
                continue
            
            for node_name, node_output in chunk.items():
                # Skip if node_output is not a dict (e.g., Overwrite objects)
                if not isinstance(node_output, dict):
                    continue
                
                if "messages" in node_output:
                    messages = node_output["messages"]
                    # Handle both list and single message
                    if not isinstance(messages, list):
                        messages = [messages]
                    
                    for msg in messages:
                        if isinstance(msg, AIMessage):
                            # Check if it's a tool call
                            if hasattr(msg, "tool_calls") and msg.tool_calls:
                                for tool_call in msg.tool_calls:
                                    tool_name = tool_call.get("name", "unknown")
                                    tool_args = tool_call.get("args", {})
                                    
                                    # Check if it's a subagent call (task tool)
                                    if tool_name == "task":
                                        subagent_name = tool_args.get("name", "unknown")
                                        task_description = tool_args.get("task", "")
                                        logger.info(f"🤖 Subagent Call: {subagent_name}")
                                        if task_description:
                                            logger.info(f"   Task: {task_description[:100]}{'...' if len(task_description) > 100 else ''}")
                                    else:
                                        # Regular tool call
                                        logger.info(f"🔧 Tool Call: {tool_name}")
                                        if tool_args:
                                            # Show key args (truncate long values)
                                            args_str = ", ".join([
                                                f"{k}={str(v)[:50]}{'...' if len(str(v)) > 50 else ''}"
                                                for k, v in tool_args.items()
                                            ])
                                            if args_str:
                                                logger.info(f"   Args: {args_str}")
                            # Regular AI message (no tool calls)
                            elif msg.content and len(str(msg.content).strip()) > 0:
                                content = str(msg.content).strip()
                                # Only show if it's substantial (not just empty or tool responses)
                                if len(content) > 20:
                                    logger.info(f"💬 AI: {content[:200]}{'...' if len(content) > 200 else ''}")
                        elif isinstance(msg, ToolMessage):
                            tool_name = getattr(msg, "name", "unknown")
                            content = str(msg.content)[:200] if msg.content else ""
                            logger.info(f"✅ Tool Result ({tool_name}): {content}{'...' if len(str(msg.content or '')) > 200 else ''}")
                        elif isinstance(msg, HumanMessage):
                            # Skip user messages in stream
                            pass
            
            # Keep track of final result (only if it's a dict with messages)
            if isinstance(chunk, dict):
                for node_output in chunk.values():
                    if isinstance(node_output, dict) and "messages" in node_output:
                        final_result = node_output
                        break
        
        return final_result if final_result else {"messages": []}
    else:
        # Non-streaming mode
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": message}]
        }, config=config)
        
        return result


def invoke_modular_agent(message: str, thread_id: str = "default", root_dir: str = None, stream: bool = False):
    """
    Invoke the modular DevOps deep agent (synchronous wrapper for async).
    
    Args:
        message: User's request
        thread_id: Thread ID for conversation persistence
        root_dir: Optional root directory for file operations.
                 If None, uses current working directory.
                 This determines where file system tools (ls, read_file, etc.) operate.
        stream: If True, stream outputs showing tool calls, subagent calls, and AI messages
        
    Returns:
        Agent response with messages, todos, etc.
    """
    import asyncio
    
    # Run the async version
    return asyncio.run(invoke_modular_agent_async(message, thread_id, root_dir, stream))


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Modular DevOps Deep Agent (CompiledSubAgent Pattern)")
    print("="*60)
    print("\nFeatures:")
    print("  ✓ CompiledSubAgent for all subagents")
    print("  ✓ Modular subagent design")
    print("  ✓ Context quarantine")
    print("  ✓ Concise output format")
    print("  ✓ Best practices from deepagents docs")
    print("\nReady!")
    
    # Example usage
    result = invoke_modular_agent("Hello! What can you help me with?", "demo")
    print("\nAgent response:")
    print(result["messages"][-1].content)

