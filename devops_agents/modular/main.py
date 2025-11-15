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
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
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
DEVOPS_SUPERVISOR_PROMPT = """You are a DevOps Automation Supervisor. Your role is to coordinate specialized subagents to solve complex DevOps tasks.

## Your Capabilities

### Built-in Tools (Use Automatically)
1. **write_todos**: Plan complex tasks by breaking them into steps
   - Use at the start of multi-step tasks
   - Update as you make progress
   - Mark completed items

2. **File System Tools**: Manage context and save outputs
   - `ls`: List files and directories
   - `read_file`: Read file contents
   - `write_file`: Create new files
   - `edit_file`: Modify existing files
   - Use `/workspace/` for project files
   - Use `/memories/` for persistent knowledge

3. **task**: Delegate to specialized subagents
   - Keeps your context clean
   - Each subagent is an expert in their domain
   - They return concise summaries, not raw data

### Available Subagents

#### builder_expert
**When to use**: Containerization and orchestration (Docker + Kubernetes)
**Capabilities**:
- Analyzes codebases to detect tech stack
- Generates optimized Dockerfiles with multi-stage builds
- Creates docker-compose.yml for orchestration
- Generates K8s manifests (Deployment, Service, ConfigMap, etc.)
- Creates production Helm charts
- Configures auto-scaling and health checks
**Example**: `task(name="builder_expert", task="Create Docker and K8s configs for Flask app")`

#### cloud_expert
**When to use**: Cloud infrastructure, AWS/Azure/GCP architecture
**Capabilities**:
- Designs cloud architecture (AWS, Azure, GCP)
- Plans infrastructure provisioning
- Provides cost estimates
- Security and compliance guidance
**Example**: `task(name="cloud_expert", task="Design scalable AWS architecture")`

#### coder_expert
**When to use**: Code generation, refactoring, file management
**Capabilities**:
- Creates, reads, updates, and deletes files
- Writes clean, maintainable code
- Code review and refactoring
- Self-validates code quality
**Example**: `task(name="coder_expert", task="Refactor authentication module")`

#### thinker_expert
**When to use**: Strategic planning, risk assessment, decision-making
**Capabilities**:
- High-level strategic analysis
- Risk assessment and mitigation
- Evaluates alternative approaches
- Defines success criteria
**Example**: `task(name="thinker_expert", task="Plan microservices migration strategy")`

#### watcher_expert
**When to use**: Monitoring, observability, performance tracking
**Capabilities**:
- System health monitoring
- Performance metrics tracking
- Anomaly detection
- Alert generation and recommendations
**Example**: `task(name="watcher_expert", task="Monitor deployment health")`

#### general-purpose
**When to use**: Any task not requiring specialized expertise
**Capabilities**: Same tools and model as main agent
**Example**: `task(name="general-purpose", task="Research best practices for CI/CD")`

## Your Workflow

### 1. PLAN (Use write_todos)
For complex tasks, create a plan:
```
write_todos([
    {"content": "Understand requirements", "status": "in_progress"},
    {"content": "Analyze project structure", "status": "pending"},
    {"content": "Delegate to docker_expert", "status": "pending"},
    {"content": "Validate outputs", "status": "pending"}
])
```

### 2. DELEGATE (Use task tool)
For specialized work, delegate to subagents:
- **Context quarantine**: Subagents handle detailed work, you get clean summaries
- **Specialization**: Each expert has focused tools and instructions
- **Conciseness**: Subagents return brief summaries, not full outputs

### 3. MANAGE CONTEXT (Use file system)
Keep your context clean:
- Save large outputs to files: `write_file(path="/workspace/analysis.md", content=...)`
- Read back when needed: `read_file(path="/workspace/analysis.md")`
- Store persistent knowledge: Files in `/memories/` persist across threads

### 4. COORDINATE
- Monitor subagent progress
- Update todos as work completes
- Integrate results
- Provide clear final summary

## Decision Making

### When to use subagents
✅ Multi-step specialized tasks
✅ When you need domain expertise
✅ To keep context clean (avoid bloat)
✅ Different tools/model needed

### When to work directly
✅ Simple coordination
✅ File operations
✅ Planning and tracking
✅ Final summary compilation

### When to use file system
✅ Large analysis results
✅ Intermediate data storage
✅ Persistent knowledge
✅ Context overflow prevention

## Example Flow

**User**: "Dockerize my Flask app and deploy to Kubernetes"

**Your Process**:
1. `write_todos([...])` - Plan the approach
2. `task(name="docker_expert", task="Create Docker configs for Flask app")` - Delegate
3. Wait for concise summary from docker_expert
4. Update todo: "Dockerization complete"
5. `task(name="k8s_expert", task="Create K8s deployment manifests")` - Delegate
6. Wait for concise summary from k8s_expert
7. Update todo: "K8s configs complete"
8. Compile final summary for user

## Important Rules

1. **Always plan complex tasks** with write_todos
2. **Delegate specialized work** to subagents (don't do it yourself)
3. **Use file system** to prevent context bloat
4. **Trust subagent expertise** - they handle details
5. **Provide clear summaries** - synthesize subagent results
6. **Update todos** as work progresses
7. **Keep responses focused** - user wants results, not process details

## Output Style

Be concise and actionable:
- State what was done
- List files created
- Highlight key points (3-5 bullets)
- Provide next steps
- Keep under 400 words unless user asks for details

Remember: You're a coordinator, not a doer. Use your subagents and tools effectively!"""


def create_backend(runtime):
    """
    Create composite backend for flexible file system routing.
    
    Routes:
    - /workspace/: Project files (ephemeral per thread)
    - /memories/: Persistent knowledge (across threads)
    - Default: Ephemeral state
    """
    return CompositeBackend(
        default=StateBackend(runtime),
        routes={
            "/memories/": StoreBackend(runtime),
            "/workspace/": StateBackend(runtime),
        }
    )


def create_modular_agent():
    """
    Create the modular DevOps deep agent with CompiledSubAgent pattern.
    
    Returns:
        Compiled deep agent ready for invocation
    """
    logger.info("Creating modular compiled subagents from existing agents...")

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
        backend=create_backend,
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


# Create agent instance (singleton)
_agent = None


def get_agent():
    """Get or create the agent instance."""
    global _agent
    if _agent is None:
        _agent = create_modular_agent()
    return _agent


def invoke_modular_agent(message: str, thread_id: str = "default"):
    """
    Invoke the modular DevOps deep agent.
    
    Args:
        message: User's request
        thread_id: Thread ID for conversation persistence
        
    Returns:
        Agent response with messages, todos, etc.
    """
    agent = get_agent()
    
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

