"""
Watcher Subagent - Wraps WatcherAgent for DeepAgents integration

Uses the existing WatcherAgent for monitoring and observability.
"""

from agents.WatcherAgent.agent import agent as watcher_agent


def create_watcher_subagent():
    """
    Create watcher subagent using the existing WatcherAgent.
    
    WatcherAgent specializes in:
    - System health monitoring
    - Performance metrics tracking
    - Anomaly detection
    - Alert generation
    - Observability recommendations
    - Agent coordination monitoring
    
    Uses WATCH Framework:
    - Warn: Identify potential issues early
    - Analyze: Examine metrics and patterns
    - Track: Monitor key performance indicators
    - Communicate: Alert relevant parties
    - Heal: Recommend remediation actions
    
    Returns:
        Compiled LangGraph graph for monitoring operations
    """
    return watcher_agent

