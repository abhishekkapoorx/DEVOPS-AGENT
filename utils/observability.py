"""
Observability and Monitoring Integration for Deep Agents

This module provides comprehensive observability through:
- LangSmith tracing integration
- Performance metrics tracking
- Error monitoring and alerting
- Agent execution analytics
- Custom instrumentation
"""

import os
from typing import Optional, Dict, Any, Callable
from functools import wraps
import time
from datetime import datetime
from loguru import logger


class ObservabilityManager:
    """
    Manages observability and monitoring for agent systems.
    
    Integrates with LangSmith for distributed tracing and monitoring.
    """
    
    def __init__(
        self,
        project_name: Optional[str] = None,
        enable_langsmith: bool = True,
        enable_metrics: bool = True,
    ):
        """
        Initialize observability manager.
        
        Args:
            project_name: LangSmith project name
            enable_langsmith: Whether to enable LangSmith tracing
            enable_metrics: Whether to track custom metrics
        """
        self.project_name = project_name or os.getenv("LANGCHAIN_PROJECT", "devops-agent")
        self.enable_langsmith = enable_langsmith
        self.enable_metrics = enable_metrics
        self.metrics = {}
        
        self._setup_langsmith()
    
    def _setup_langsmith(self):
        """Configure LangSmith tracing."""
        if not self.enable_langsmith:
            logger.info("LangSmith tracing disabled")
            return
        
        # Check if LangSmith is configured
        api_key = os.getenv("LANGCHAIN_API_KEY")
        if not api_key:
            logger.warning(
                "LANGCHAIN_API_KEY not set. LangSmith tracing will not be available. "
                "Set LANGCHAIN_API_KEY and LANGCHAIN_TRACING_V2=true to enable."
            )
            self.enable_langsmith = False
            return
        
        # Enable tracing
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_PROJECT"] = self.project_name
        
        # Optional: Set endpoint if using self-hosted LangSmith
        langsmith_endpoint = os.getenv("LANGCHAIN_ENDPOINT")
        if langsmith_endpoint:
            os.environ["LANGCHAIN_ENDPOINT"] = langsmith_endpoint
        
        logger.info(f"LangSmith tracing enabled for project: {self.project_name}")
    
    def track_metric(self, metric_name: str, value: Any, metadata: Optional[Dict] = None):
        """
        Track a custom metric.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            metadata: Optional metadata about the metric
        """
        if not self.enable_metrics:
            return
        
        timestamp = datetime.utcnow().isoformat()
        
        if metric_name not in self.metrics:
            self.metrics[metric_name] = []
        
        self.metrics[metric_name].append({
            "value": value,
            "timestamp": timestamp,
            "metadata": metadata or {},
        })
        
        logger.debug(f"Metric tracked: {metric_name} = {value}")
    
    def get_metrics(self, metric_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get tracked metrics.
        
        Args:
            metric_name: Optional specific metric to retrieve
            
        Returns:
            Dictionary of metrics
        """
        if metric_name:
            return {metric_name: self.metrics.get(metric_name, [])}
        return self.metrics
    
    def clear_metrics(self):
        """Clear all tracked metrics."""
        self.metrics = {}
        logger.info("Metrics cleared")
    
    def instrument_function(
        self,
        name: Optional[str] = None,
        track_time: bool = True,
        track_errors: bool = True,
    ):
        """
        Decorator to instrument a function with observability.
        
        Args:
            name: Custom name for the function (defaults to function name)
            track_time: Whether to track execution time
            track_errors: Whether to track errors
            
        Returns:
            Decorated function
        """
        def decorator(func: Callable) -> Callable:
            func_name = name or func.__name__
            
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                error = None
                result = None
                
                try:
                    result = await func(*args, **kwargs)
                    return result
                    
                except Exception as e:
                    error = e
                    if track_errors:
                        self.track_metric(
                            f"{func_name}_errors",
                            1,
                            {"error_type": type(e).__name__, "error_msg": str(e)}
                        )
                    raise
                    
                finally:
                    if track_time:
                        duration = time.time() - start_time
                        self.track_metric(
                            f"{func_name}_duration",
                            duration,
                            {"success": error is None}
                        )
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.time()
                error = None
                result = None
                
                try:
                    result = func(*args, **kwargs)
                    return result
                    
                except Exception as e:
                    error = e
                    if track_errors:
                        self.track_metric(
                            f"{func_name}_errors",
                            1,
                            {"error_type": type(e).__name__, "error_msg": str(e)}
                        )
                    raise
                    
                finally:
                    if track_time:
                        duration = time.time() - start_time
                        self.track_metric(
                            f"{func_name}_duration",
                            duration,
                            {"success": error is None}
                        )
            
            # Return appropriate wrapper based on function type
            import inspect
            if inspect.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
        
        return decorator
    
    def create_run_metadata(
        self,
        agent_name: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **custom_metadata
    ) -> Dict[str, Any]:
        """
        Create metadata for a run that will be sent to LangSmith.
        
        Args:
            agent_name: Name of the agent
            user_id: Optional user identifier
            session_id: Optional session identifier
            **custom_metadata: Additional custom metadata
            
        Returns:
            Metadata dictionary
        """
        metadata = {
            "agent_name": agent_name,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        if user_id:
            metadata["user_id"] = user_id
        
        if session_id:
            metadata["session_id"] = session_id
        
        metadata.update(custom_metadata)
        
        return metadata
    
    def get_langsmith_config(
        self,
        run_name: Optional[str] = None,
        tags: Optional[list] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Get configuration dictionary for LangSmith tracing.
        
        Args:
            run_name: Name for this run in LangSmith
            tags: List of tags for filtering/organizing runs
            metadata: Additional metadata
            
        Returns:
            Configuration dictionary to pass to agent.invoke()
        """
        if not self.enable_langsmith:
            return {}
        
        config = {}
        
        if run_name:
            config["run_name"] = run_name
        
        if tags:
            config["tags"] = tags
        
        if metadata:
            config["metadata"] = metadata
        
        return config


# Global observability manager instance
_observability_manager: Optional[ObservabilityManager] = None


def get_observability_manager(**kwargs) -> ObservabilityManager:
    """
    Get the global observability manager (singleton pattern).
    
    Args:
        **kwargs: Configuration options (only used on first call)
        
    Returns:
        ObservabilityManager instance
    """
    global _observability_manager
    
    if _observability_manager is None:
        _observability_manager = ObservabilityManager(**kwargs)
    
    return _observability_manager


def setup_observability(
    project_name: Optional[str] = None,
    enable_langsmith: Optional[bool] = None,
):
    """
    Setup observability for the agent system.
    
    Args:
        project_name: LangSmith project name
        enable_langsmith: Whether to enable LangSmith
    """
    # Get configuration from environment if not provided
    if enable_langsmith is None:
        enable_langsmith = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    
    if project_name is None:
        project_name = os.getenv("LANGCHAIN_PROJECT", "devops-agent")
    
    manager = get_observability_manager(
        project_name=project_name,
        enable_langsmith=enable_langsmith,
    )
    
    logger.info("Observability system initialized")
    return manager


def track_agent_execution(
    agent_name: str,
    session_id: Optional[str] = None,
    **metadata
):
    """
    Decorator to track agent execution in LangSmith.
    
    Args:
        agent_name: Name of the agent
        session_id: Optional session ID
        **metadata: Additional metadata
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            manager = get_observability_manager()
            
            # Add LangSmith config if enabled
            if manager.enable_langsmith:
                run_metadata = manager.create_run_metadata(
                    agent_name=agent_name,
                    session_id=session_id,
                    **metadata
                )
                
                langsmith_config = manager.get_langsmith_config(
                    run_name=f"{agent_name}_execution",
                    tags=[agent_name, "deep_agent"],
                    metadata=run_metadata,
                )
                
                # Merge with existing config if present
                if "config" in kwargs:
                    kwargs["config"].update(langsmith_config)
                else:
                    kwargs["config"] = langsmith_config
            
            return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            manager = get_observability_manager()
            
            # Add LangSmith config if enabled
            if manager.enable_langsmith:
                run_metadata = manager.create_run_metadata(
                    agent_name=agent_name,
                    session_id=session_id,
                    **metadata
                )
                
                langsmith_config = manager.get_langsmith_config(
                    run_name=f"{agent_name}_execution",
                    tags=[agent_name, "deep_agent"],
                    metadata=run_metadata,
                )
                
                # Merge with existing config if present
                if "config" in kwargs:
                    kwargs["config"].update(langsmith_config)
                else:
                    kwargs["config"] = langsmith_config
            
            return func(*args, **kwargs)
        
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


# Convenience function for agent invocation with observability
def invoke_with_observability(
    agent,
    input_data: Dict[str, Any],
    agent_name: str,
    session_id: Optional[str] = None,
    tags: Optional[list] = None,
    **kwargs
):
    """
    Invoke an agent with full observability enabled.
    
    Args:
        agent: The agent to invoke
        input_data: Input data for the agent
        agent_name: Name of the agent
        session_id: Optional session ID
        tags: Optional tags
        **kwargs: Additional arguments for agent.invoke()
        
    Returns:
        Agent invocation result
    """
    manager = get_observability_manager()
    
    # Create configuration
    run_metadata = manager.create_run_metadata(
        agent_name=agent_name,
        session_id=session_id,
    )
    
    config = manager.get_langsmith_config(
        run_name=f"{agent_name}_invocation",
        tags=tags or [agent_name, "deep_agent"],
        metadata=run_metadata,
    )
    
    # Merge with existing config
    if "config" in kwargs:
        kwargs["config"].update(config)
    else:
        kwargs["config"] = config
    
    # Track start time
    start_time = time.time()
    
    try:
        result = agent.invoke(input_data, **kwargs)
        duration = time.time() - start_time
        
        # Track success metric
        manager.track_metric(
            f"{agent_name}_invocations",
            1,
            {"success": True, "duration": duration}
        )
        
        return result
        
    except Exception as e:
        duration = time.time() - start_time
        
        # Track failure metric
        manager.track_metric(
            f"{agent_name}_invocations",
            1,
            {"success": False, "duration": duration, "error": str(e)}
        )
        
        raise


# Initialize on import
logger.info("Observability module loaded")

