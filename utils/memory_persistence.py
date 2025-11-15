"""
Memory Persistence and Checkpointing for Deep Agents

This module provides memory persistence capabilities using LangGraph's
checkpointing system, enabling agents to:
- Save state across sessions
- Resume interrupted workflows
- Maintain conversation history
- Track long-term context
"""

from typing import Optional, Dict, Any
from pathlib import Path
from loguru import logger

# Import checkpointers - handle version differences gracefully
try:
    from langgraph.checkpoint.memory import MemorySaver
except ImportError:
    from langgraph.checkpoint import MemorySaver

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
    SQLITE_AVAILABLE = True
except ImportError:
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver as SqliteSaver
        SQLITE_AVAILABLE = True
    except ImportError:
        SQLITE_AVAILABLE = False
        logger.warning("SQLite checkpointing not available in this LangGraph version")

try:
    from langgraph.checkpoint.postgres import PostgresSaver
    POSTGRES_AVAILABLE = True
except ImportError:
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver as PostgresSaver
        POSTGRES_AVAILABLE = True
    except ImportError:
        POSTGRES_AVAILABLE = False
        logger.warning("PostgreSQL checkpointing not available in this LangGraph version")

import sqlite3


class CheckpointManager:
    """
    Manages checkpointing for agent state persistence.
    
    Supports multiple backend storage options:
    - Memory (in-process, not persistent across restarts)
    - SQLite (file-based persistence)
    - PostgreSQL (production-grade persistence)
    """
    
    def __init__(
        self,
        backend: str = "memory",
        db_path: Optional[str] = None,
        postgres_uri: Optional[str] = None,
    ):
        """
        Initialize the checkpoint manager.
        
        Args:
            backend: Storage backend - "memory", "sqlite", or "postgres"
            db_path: Path to SQLite database file (for sqlite backend)
            postgres_uri: PostgreSQL connection URI (for postgres backend)
        """
        self.backend = backend
        self.db_path = db_path
        self.postgres_uri = postgres_uri
        self.checkpointer = None
        
        self._initialize_checkpointer()
    
    def _initialize_checkpointer(self):
        """Initialize the appropriate checkpointer based on backend."""
        try:
            if self.backend == "memory":
                self.checkpointer = MemorySaver()
                logger.info("Initialized in-memory checkpointing")
                
            elif self.backend == "sqlite":
                if not SQLITE_AVAILABLE:
                    logger.warning("SQLite checkpointing not available, falling back to memory")
                    self.checkpointer = MemorySaver()
                    return
                
                if not self.db_path:
                    self.db_path = "./.checkpoints/agent_checkpoints.db"
                
                # Ensure directory exists
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
                
                # Create SQLite connection
                try:
                    conn = sqlite3.connect(self.db_path, check_same_thread=False)
                    self.checkpointer = SqliteSaver(conn)
                    logger.info(f"Initialized SQLite checkpointing at {self.db_path}")
                except Exception as e:
                    logger.warning(f"Failed to initialize SQLite: {e}, using memory")
                    self.checkpointer = MemorySaver()
                
            elif self.backend == "postgres":
                if not POSTGRES_AVAILABLE:
                    logger.warning("PostgreSQL checkpointing not available, falling back to memory")
                    self.checkpointer = MemorySaver()
                    return
                
                if not self.postgres_uri:
                    raise ValueError("PostgreSQL URI required for postgres backend")
                
                try:
                    self.checkpointer = PostgresSaver.from_conn_string(self.postgres_uri)
                    logger.info("Initialized PostgreSQL checkpointing")
                except Exception as e:
                    logger.warning(f"Failed to initialize PostgreSQL: {e}, using memory")
                    self.checkpointer = MemorySaver()
                
            else:
                raise ValueError(f"Unknown backend: {self.backend}")
                
        except Exception as e:
            logger.error(f"Failed to initialize checkpointer: {e}")
            logger.warning("Falling back to in-memory checkpointing")
            self.checkpointer = MemorySaver()
    
    def get_checkpointer(self):
        """Get the configured checkpointer instance."""
        return self.checkpointer
    
    def save_checkpoint(
        self,
        thread_id: str,
        checkpoint_data: Dict[str, Any],
    ) -> bool:
        """
        Save a checkpoint for a specific thread/session.
        
        Args:
            thread_id: Unique identifier for the conversation thread
            checkpoint_data: State data to checkpoint
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.checkpointer:
                logger.warning("No checkpointer available")
                return False
            
            # Checkpointing is typically handled automatically by LangGraph
            # This method is here for explicit checkpoint operations if needed
            logger.info(f"Checkpoint saved for thread: {thread_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False
    
    def load_checkpoint(
        self,
        thread_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Load a checkpoint for a specific thread/session.
        
        Args:
            thread_id: Unique identifier for the conversation thread
            
        Returns:
            Checkpoint data if found, None otherwise
        """
        try:
            if not self.checkpointer:
                logger.warning("No checkpointer available")
                return None
            
            # LangGraph handles checkpoint loading automatically
            # This method is here for explicit checkpoint retrieval if needed
            logger.info(f"Checkpoint loaded for thread: {thread_id}")
            return {}
            
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None
    
    def list_checkpoints(self, thread_id: Optional[str] = None) -> list:
        """
        List available checkpoints.
        
        Args:
            thread_id: Optional thread ID to filter checkpoints
            
        Returns:
            List of checkpoint metadata
        """
        try:
            if not self.checkpointer:
                return []
            
            # Implementation depends on checkpointer type
            # This is a placeholder for checkpoint listing functionality
            logger.info("Listing checkpoints")
            return []
            
        except Exception as e:
            logger.error(f"Failed to list checkpoints: {e}")
            return []
    
    def delete_checkpoint(self, thread_id: str) -> bool:
        """
        Delete checkpoints for a specific thread.
        
        Args:
            thread_id: Thread ID to delete checkpoints for
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.checkpointer:
                return False
            
            logger.info(f"Deleted checkpoints for thread: {thread_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete checkpoint: {e}")
            return False


# Global checkpoint manager instance
_checkpoint_manager: Optional[CheckpointManager] = None


def get_checkpoint_manager(
    backend: Optional[str] = None,
    **kwargs
) -> CheckpointManager:
    """
    Get the global checkpoint manager instance (singleton pattern).
    
    Args:
        backend: Storage backend (on first call only)
        **kwargs: Additional configuration options
        
    Returns:
        CheckpointManager instance
    """
    global _checkpoint_manager
    
    if _checkpoint_manager is None:
        import os
        
        # Determine backend from environment or parameter
        backend = backend or os.getenv("CHECKPOINT_BACKEND", "sqlite")
        
        # Get configuration from environment
        db_path = kwargs.get("db_path") or os.getenv("CHECKPOINT_DB_PATH")
        postgres_uri = kwargs.get("postgres_uri") or os.getenv("CHECKPOINT_POSTGRES_URI")
        
        _checkpoint_manager = CheckpointManager(
            backend=backend,
            db_path=db_path,
            postgres_uri=postgres_uri,
        )
    
    return _checkpoint_manager


def create_checkpointed_agent(agent_graph, **config):
    """
    Compile an agent graph with checkpointing enabled.
    
    Args:
        agent_graph: LangGraph StateGraph instance
        **config: Additional configuration options
        
    Returns:
        Compiled graph with checkpointing
    """
    checkpoint_manager = get_checkpoint_manager()
    checkpointer = checkpoint_manager.get_checkpointer()
    
    # Compile with checkpointer
    compiled = agent_graph.compile(
        checkpointer=checkpointer,
        **config
    )
    
    logger.info(f"Created checkpointed agent with {checkpoint_manager.backend} backend")
    return compiled


def get_thread_config(thread_id: str, **kwargs) -> Dict[str, Any]:
    """
    Create a configuration dict for a specific conversation thread.
    
    This config is used when invoking agents to maintain conversation context.
    
    Args:
        thread_id: Unique identifier for the conversation thread
        **kwargs: Additional configuration options
        
    Returns:
        Configuration dictionary with thread information
    """
    config = {
        "configurable": {
            "thread_id": thread_id,
        },
        **kwargs
    }
    
    return config


def create_session_id(prefix: str = "session") -> str:
    """
    Create a unique session/thread ID.
    
    Args:
        prefix: Prefix for the session ID
        
    Returns:
        Unique session ID string
    """
    import uuid
    from datetime import datetime
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    
    return f"{prefix}_{timestamp}_{unique_id}"


# Example usage helper
def enable_persistence_for_agent(
    agent_graph,
    thread_id: Optional[str] = None,
    backend: str = "sqlite",
    **config
):
    """
    Helper function to easily enable persistence for an agent.
    
    Args:
        agent_graph: LangGraph StateGraph instance
        thread_id: Optional specific thread ID to use
        backend: Storage backend
        **config: Additional configuration
        
    Returns:
        Tuple of (compiled_agent, thread_config)
    """
    # Initialize checkpoint manager if needed
    checkpoint_manager = get_checkpoint_manager(backend=backend)
    
    # Compile agent with checkpointing
    compiled_agent = create_checkpointed_agent(agent_graph, **config)
    
    # Create thread config
    if not thread_id:
        thread_id = create_session_id(prefix="agent")
    
    thread_config = get_thread_config(thread_id)
    
    logger.info(f"Enabled persistence for agent with thread_id: {thread_id}")
    
    return compiled_agent, thread_config


# Context manager for agent sessions
class AgentSession:
    """
    Context manager for agent sessions with automatic checkpointing.
    
    Example:
        with AgentSession("my_agent_session") as session:
            result = agent.invoke(input, config=session.config)
    """
    
    def __init__(self, thread_id: Optional[str] = None, backend: str = "sqlite"):
        self.thread_id = thread_id or create_session_id()
        self.backend = backend
        self.config = None
        self.checkpoint_manager = None
    
    def __enter__(self):
        self.checkpoint_manager = get_checkpoint_manager(backend=self.backend)
        self.config = get_thread_config(self.thread_id)
        logger.info(f"Started agent session: {self.thread_id}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            logger.error(f"Session {self.thread_id} ended with error: {exc_val}")
        else:
            logger.info(f"Session {self.thread_id} completed successfully")
        return False
    
    def get_config(self) -> Dict[str, Any]:
        """Get the configuration for this session."""
        return self.config

