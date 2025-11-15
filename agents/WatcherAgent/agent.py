"""
Watcher Agent - Monitoring and Observability

This deep agent specializes in:
- System health monitoring
- Performance metrics tracking
- Anomaly detection
- Alert generation
- Observability recommendations
- Agent coordination monitoring
"""

from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage, HumanMessage
from typing import Dict, Any, List
from datetime import datetime
from loguru import logger

from llms import DEFAULT_MODEL
from utils.deep_agent_state import WatcherAgentState, create_initial_reflection_state
from utils.context_middleware import (
    bind_context_before_model,
    bind_context_for_tools,
)


WATCHER_AGENT_PROMPT = """# Watcher Agent - Monitoring and Observability

## Role and Purpose
You are a monitoring and observability agent responsible for tracking system health,
performance metrics, and detecting anomalies across the agent ecosystem.

## Core Capabilities
1. **Health Monitoring**: Track agent and system health status
2. **Performance Metrics**: Monitor execution times, resource usage, success rates
3. **Anomaly Detection**: Identify unusual patterns or behaviors
4. **Alert Generation**: Create actionable alerts for issues
5. **Observability Recommendations**: Suggest improvements to monitoring
6. **Coordination Tracking**: Monitor inter-agent communication and handoffs

## Monitoring Framework - WATCH
**W**arn: Identify potential issues before they become critical
**A**nalyze: Examine metrics and patterns for insights
**T**rack: Continuously monitor key performance indicators
**C**ommunicate: Alert relevant parties of important findings
**H**eal: Recommend or trigger remediation actions

## Key Metrics to Monitor
1. **Agent Performance**
   - Execution time per agent
   - Success/failure rates
   - Tool usage patterns
   - Token consumption
   - Reflection iterations

2. **System Health**
   - Error rates and types
   - Retry counts
   - Timeout occurrences
   - Resource utilization

3. **Quality Metrics**
   - Confidence scores
   - Revision frequencies
   - User satisfaction indicators

4. **Coordination Metrics**
   - Handoff success rates
   - Inter-agent communication delays
   - Plan adherence

## Output Format
### System Health Status
[HEALTHY | DEGRADED | CRITICAL]: Brief overall status

### Performance Metrics
[Key metrics with values and trends]

### Anomalies Detected
[Any unusual patterns or behaviors]

### Active Alerts
[Current alerts requiring attention]

### Recommendations
[Suggested improvements or actions]

## Alert Severity Levels
- **CRITICAL**: Immediate action required, system functionality impaired
- **HIGH**: Significant issue, attention needed soon
- **MEDIUM**: Notable issue, should be addressed
- **LOW**: Minor issue or optimization opportunity
- **INFO**: Informational, no action required

## Principles
- Be proactive, not just reactive
- Provide context with every alert
- Suggest concrete remediation steps
- Track trends, not just point-in-time metrics
- Balance between noise and signal
- Protect user privacy in logs

Begin monitoring and await status requests or anomaly reports."""


def create_watcher_agent() -> StateGraph:
    """
    Create the Watcher Agent with monitoring capabilities.
    
    Returns:
        Compiled LangGraph with watcher agent nodes
    """
    
    # Create the agent
    agent = create_agent(
        model=DEFAULT_MODEL,
        tools=[],  # Could add monitoring tools like metrics queries
        name="watcher_agent",
        system_prompt=WATCHER_AGENT_PROMPT,
        middleware=[bind_context_before_model, bind_context_for_tools],
    )
    
    # Define monitoring node
    async def monitor_node(state: WatcherAgentState) -> Dict[str, Any]:
        """Main monitoring node."""
        try:
            logger.info("Watcher Agent: Performing system monitoring")
            
            # Collect metrics from state
            metrics = _collect_metrics(state)
            
            # Detect anomalies
            anomalies = _detect_anomalies(state, metrics)
            
            # Generate health status
            health_status = _assess_health(metrics, anomalies)
            
            # Update state with monitoring info
            monitoring_report = f"""
System Health: {health_status}

Performance Metrics:
{_format_metrics(metrics)}

Anomalies: {len(anomalies)} detected
{_format_anomalies(anomalies)}
"""
            
            # Add monitoring report to messages for agent analysis
            messages = state.get("messages", [])
            messages = messages + [HumanMessage(content=f"Monitoring Report:\n{monitoring_report}")]
            
            # Invoke agent to analyze and provide recommendations
            result = await agent.ainvoke({**state, "messages": messages})
            
            return {
                **result,
                "system_health": health_status,
                "performance_metrics": metrics,
                "anomalies_detected": anomalies,
                "current_step": "monitoring_complete",
            }
            
        except Exception as e:
            logger.error(f"Watcher Agent error: {e}")
            return {
                **state,
                "last_error": str(e),
                "system_health": "UNKNOWN",
                "errors": state.get("errors", []) + [{"error": str(e), "node": "watcher"}],
            }
    
    # Define alert generation node
    async def alert_node(state: WatcherAgentState) -> Dict[str, Any]:
        """Generate alerts based on anomalies and health status."""
        try:
            anomalies = state.get("anomalies_detected", [])
            health_status = state.get("system_health", "UNKNOWN")
            alerts = state.get("alerts", [])
            
            # Generate new alerts
            new_alerts = []
            
            # Critical health alert
            if health_status == "CRITICAL":
                new_alerts.append({
                    "severity": "CRITICAL",
                    "message": "System health is critical",
                    "timestamp": datetime.utcnow().isoformat(),
                    "recommendation": "Review error logs and recent failures",
                })
            
            # Anomaly alerts
            for anomaly in anomalies:
                new_alerts.append({
                    "severity": "MEDIUM",
                    "message": f"Anomaly detected: {anomaly}",
                    "timestamp": datetime.utcnow().isoformat(),
                    "recommendation": "Investigate anomaly cause",
                })
            
            return {
                **state,
                "alerts": alerts + new_alerts,
            }
            
        except Exception as e:
            logger.error(f"Alert generation error: {e}")
            return state
    
    # Build the graph
    graph = StateGraph(WatcherAgentState)
    
    # Add nodes
    graph.add_node("monitor", monitor_node)
    graph.add_node("alert", alert_node)
    
    # Add edges
    graph.add_edge(START, "monitor")
    graph.add_edge("monitor", "alert")
    graph.add_edge("alert", END)
    
    return graph


def _collect_metrics(state: Dict[str, Any]) -> Dict[str, Any]:
    """Collect performance metrics from state."""
    metrics = {
        "execution_time": 0.0,
        "total_messages": len(state.get("messages", [])),
        "errors_count": len(state.get("errors", [])),
        "retry_count": state.get("retry_count", 0),
        "revision_count": state.get("revision_count", 0),
        "confidence_score": state.get("confidence_score", 1.0),
        "tokens_used": state.get("tokens_used", 0),
        "tool_calls_count": len(state.get("tool_calls", [])),
        "completed_steps": len(state.get("completed_steps", [])),
    }
    
    # Calculate execution time if available
    start_time = state.get("execution_start_time")
    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time)
            elapsed = (datetime.utcnow() - start_dt).total_seconds()
            metrics["execution_time"] = elapsed
        except:
            pass
    
    return metrics


def _detect_anomalies(state: Dict[str, Any], metrics: Dict[str, Any]) -> List[str]:
    """Detect anomalies in metrics."""
    anomalies = []
    
    # High retry count
    if metrics["retry_count"] > 2:
        anomalies.append(f"High retry count: {metrics['retry_count']}")
    
    # Multiple revisions
    if metrics["revision_count"] > 2:
        anomalies.append(f"Multiple revisions required: {metrics['revision_count']}")
    
    # Low confidence
    if metrics["confidence_score"] < 0.5:
        anomalies.append(f"Low confidence score: {metrics['confidence_score']:.2f}")
    
    # Many errors
    if metrics["errors_count"] > 3:
        anomalies.append(f"High error count: {metrics['errors_count']}")
    
    # Long execution time (> 5 minutes)
    if metrics["execution_time"] > 300:
        anomalies.append(f"Long execution time: {metrics['execution_time']:.1f}s")
    
    return anomalies


def _assess_health(metrics: Dict[str, Any], anomalies: List[str]) -> str:
    """Assess overall system health."""
    # Critical conditions
    if metrics["errors_count"] > 5 or metrics["retry_count"] > 3:
        return "CRITICAL"
    
    # Degraded conditions
    if len(anomalies) > 2 or metrics["confidence_score"] < 0.6:
        return "DEGRADED"
    
    return "HEALTHY"


def _format_metrics(metrics: Dict[str, Any]) -> str:
    """Format metrics for display."""
    lines = []
    for key, value in metrics.items():
        if isinstance(value, float):
            lines.append(f"  - {key}: {value:.2f}")
        else:
            lines.append(f"  - {key}: {value}")
    return "\n".join(lines)


def _format_anomalies(anomalies: List[str]) -> str:
    """Format anomalies for display."""
    if not anomalies:
        return "  None"
    return "\n".join(f"  - {a}" for a in anomalies)


# Create and compile the agent
agent = create_watcher_agent().compile(name="watcher_agent").with_config({"recursion_limit": 150})

