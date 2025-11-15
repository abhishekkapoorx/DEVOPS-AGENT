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
        
        # Wrap FilesystemBackend to normalize paths
        # When agent calls ls / or ls /workspace/, convert to empty string
        # so FilesystemBackend uses root_dir instead of system root
        class NormalizedFilesystemBackend:
            """Wrapper that normalizes paths to use root_dir correctly"""
            def __init__(self, backend):
                self.backend = backend
                self.cwd = backend.cwd
            
            def _normalize_path(self, path):
                """Normalize path to use root_dir instead of system root"""
                if path is None:
                    return ''
                if path == '/' or path == '/workspace' or path == '/workspace/':
                    return ''  # Use root_dir
                if path.startswith('/workspace/'):
                    return path[len('/workspace/'):]  # Strip /workspace/ prefix
                if path.startswith('/') and path != '/':
                    # Strip leading / to make relative to root_dir
                    return path.lstrip('/')
                return path
            
            def ls_info(self, path):
                normalized = self._normalize_path(path)
                return self.backend.ls_info(normalized)
            
            def read(self, file_path, offset=0, limit=2000):
                # read signature: (file_path, offset=0, limit=2000)
                normalized_path = self._normalize_path(file_path)
                return self.backend.read(normalized_path, offset, limit)
            
            def write(self, path, content):
                normalized = self._normalize_path(path)
                return self.backend.write(normalized, content)
            
            def edit(self, file_path, old_string, new_string, replace_all=False):
                # edit signature: (file_path, old_string, new_string, replace_all=False)
                normalized_path = self._normalize_path(file_path)
                return self.backend.edit(normalized_path, old_string, new_string, replace_all)
            
            def glob_info(self, pattern, path='/'):
                # Normalize the path parameter, not the pattern
                normalized_path = self._normalize_path(path)
                return self.backend.glob_info(pattern, normalized_path)
            
            def grep_raw(self, pattern, path=None, glob=None):
                # grep_raw signature: (pattern, path=None, glob=None)
                normalized_path = self._normalize_path(path) if path else None
                normalized_glob = self._normalize_path(glob) if glob else None
                return self.backend.grep_raw(pattern, normalized_path, normalized_glob)
        
        normalized_backend = NormalizedFilesystemBackend(fs_backend)
        
        # Per deepagents best practices: CompositeBackend
        # Default uses normalized FilesystemBackend for actual file access
        # /memories/ routes to StoreBackend for persistence across threads
        return CompositeBackend(
            default=normalized_backend,  # All file operations use normalized FilesystemBackend with root_dir
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


def invoke_modular_agent(message: str, thread_id: str = "default", root_dir: str = None):
    """
    Invoke the modular DevOps deep agent.
    
    Args:
        message: User's request
        thread_id: Thread ID for conversation persistence
        root_dir: Optional root directory for file operations.
                 If None, uses current working directory.
                 This determines where file system tools (ls, read_file, etc.) operate.
        
    Returns:
        Agent response with messages, todos, etc.
    """
    agent = get_agent(root_dir=root_dir)
    
    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }
    
    result = agent.invoke({
        "messages": [{"role": "user", "content": message}]
    }, config=config)
    
    return result


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

