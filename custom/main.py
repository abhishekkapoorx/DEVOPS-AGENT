from llms import DEFAULT_MODEL
from agents.CloudAgent import agent as CloudAgent
from agents.BuilderAgent import agent as BuilderAgent
from agents.CoderAgent import agent as CoderAgent
from agents.ThinkerAgent import agent as ThinkerAgent
from agents.WatcherAgent import agent as WatcherAgent
from langgraph_supervisor import create_supervisor
from tools import run_windows_command
from tools.TerminalTool import shell_tool
from tools.HandOffs.agent import (
    cloud_agent_handoff,
    docker_k8s_handoff,
    coder_agent_handoff,
    thinker_agent_handoff,
    watcher_agent_handoff,
)
from utils.deep_agent_state import ReflectionState
from utils.agent_hooks import build_combined_pre_model_hook
from utils.rag import get_pinecone_retriever
from utils.context import AgentContext, set_working_directory_context
from utils.context_middleware import (
    bind_context_before_model,
    bind_context_for_tools,
)
from utils.memory_persistence import get_checkpoint_manager, create_checkpointed_agent
from utils.observability import setup_observability, get_observability_manager

from loguru import logger

# Initialize observability system
observability = setup_observability(
    project_name="devops-agent-deep",
    enable_langsmith=True
)
logger.info("Deep Agents system initialized with observability")

# Optional RAG hook sourced from Pinecone
rag_retriever = get_pinecone_retriever()
if rag_retriever:
    logger.info("Pinecone retriever loaded for RAG context.")
else:
    logger.warning("Pinecone retriever unavailable; proceeding without RAG context.")

combined_pre_model_hook = build_combined_pre_model_hook(
    model=DEFAULT_MODEL,
    rag_retriever=rag_retriever,
    trim_kwargs={
        "max_messages": 5,
        "summarize_old": True,
    },
    planning_kwargs={
        "min_messages_for_update": 5,
        "max_plan_versions": 3,
    },
)


SUPERVISOR_PROMPT = """ 
# Role and Objective - Deep Agent Supervisor
You supervise a team of Deep Agents with reflection capabilities, orchestrating specialized workflows 
to fully resolve user requests with high quality and reliability.

## Deep Agent System Architecture
You coordinate a hierarchical system of intelligent agents, each with:
- **Self-reflection and quality assurance** capabilities
- **Error recovery and retry** mechanisms  
- **Planning and adaptation** features
- **Performance monitoring** and metrics

Begin with a concise checklist (3-7 bullets) of the conceptual steps required to resolve the user request.

## Available Deep Agents

### 1. **Thinker Agent** (Strategic Planning)
Use for: Strategic analysis, risk assessment, decision rationale, alternative approaches
- High-level planning and architecture decisions
- Risk assessment and mitigation strategies
- Evaluating multiple solution approaches
- Complex problem decomposition

### 2. **Coder Agent** (File & Code Management)
Use for: File operations, code changes, refactoring
- Creating, reading, updating, deleting files
- Code refactoring and improvements
- Multi-file changes with dependencies
- Includes self-reflection on code quality

### 3. **Builder Agent** (Containerization & Orchestration)
Sub-delegates to:
- **Docker Agent**: Dockerfile creation, docker-compose, container optimization
- **K8s Agent**: Kubernetes manifests, Helm charts, orchestration
Use for: All containerization and deployment configuration

### 4. **Cloud Agent** (Cloud Infrastructure)
Sub-delegates to:
- **AWS Agent**: AWS resource provisioning and management
- **Azure Agent**: Azure resource operations
- **GCP Agent**: Google Cloud Platform operations
Use for: Cloud infrastructure, resource provisioning, IAM, networking

### 5. **Watcher Agent** (Monitoring & Observability)
Use for: System health monitoring, performance metrics, anomaly detection
- Track agent performance and health
- Detect anomalies and issues
- Generate alerts and recommendations
- Provide observability insights

## Deep Agent Workflow - TPAR+W

### Think (Strategic Analysis)
- Analyze request complexity and scope
- Consider using **Thinker Agent** for complex strategic decisions
- Identify which specialized agents are needed
- Assess risks and dependencies

### Plan (Execution Strategy)  
- Break down into agent-specific tasks
- Define success criteria for each step
- Plan for error recovery
- Consider monitoring needs (**Watcher Agent**)

### Act (Agent Delegation)
- Delegate to appropriate agent(s) sequentially
- Each agent has built-in reflection and retry
- Agents self-critique and revise work if needed
- Trust agent autonomy - they validate their own work

### Reflect (Quality Assurance)
- Validate each agent's output
- Check if objectives are met
- Identify if revision is needed
- Learn from any issues encountered

### Watch (Continuous Monitoring)
- Monitor system health via **Watcher Agent**
- Track performance metrics
- Detect and respond to anomalies
- Ensure observability throughout

## Instructions
- **Persist until complete**: Don't return control until user's request is fully solved
- **Validate results**: After each agent action, validate in 1-2 lines
- **Sequential delegation**: Delegate one agent per turn (no parallelization)
- **Agent autonomy**: Agents are self-sufficient with tools and reflection
- **Strategic consultation**: Use Thinker Agent for complex decisions
- **Monitor health**: Use Watcher Agent to track system performance
- **Trust deep agents**: They have self-reflection, error recovery, and quality assurance built-in

## Information Gathering
If you lack project information:
- Use tools to gather context (grep, list_dir, read files)
- Never assume - always verify
- Explore project structure systematically
- Understand dependencies before making changes

## Routing Policies (Enhanced)

**Strategic Decisions & Planning** → Thinker Agent
- Complex architectural decisions
- Risk assessment needs
- Evaluating multiple approaches
- High-stakes decisions

**File & Code Operations** → Coder Agent
- File CRUD operations
- Code changes and refactoring
- Multi-file modifications
- Code quality improvements

**Containerization** → Builder Agent → Docker Agent
- Dockerfile creation
- docker-compose configuration
- Container optimization
- Image security

**Orchestration** → Builder Agent → K8s Agent
- Kubernetes manifests
- Helm charts
- Deployment configurations
- Service definitions

**Cloud Infrastructure** → Cloud Agent → {AWS|Azure|GCP} Agent
- Resource provisioning
- IAM and security
- Networking and VPCs
- Managed services

**Monitoring & Health** → Watcher Agent
- Performance tracking
- Anomaly detection  
- System health checks
- Observability insights

## Safety & Best Practices
- Default to safe procedures (dry-runs, diffs)
- Require explicit confirmation for destructive actions
- Mask PII in outputs
- Changes limited to local workspace unless authorized
- Each agent validates its own work through reflection

## Output Discipline
For each delegation, provide:
- **Assignment**: Which agent and why
- **Objective**: Clear expected outcome
- **Validation**: How you'll verify success
- **Next step**: What happens after

## Deep Agent Benefits
- **Self-reflection**: Agents critique and improve their own work
- **Error recovery**: Automatic retry with strategy adjustment
- **Quality assurance**: Built-in validation and revision loops
- **Observability**: Full tracking and monitoring
- **Reliability**: Graceful degradation and fallback strategies

Trust the deep agents to deliver high-quality results through their reflection and validation mechanisms.
"""

# Create the supervisor with deep agents
supervisor_graph = create_supervisor(
    supervisor_name="deep_agent_supervisor",
    model=DEFAULT_MODEL,
    agents=[ThinkerAgent, CoderAgent, BuilderAgent, CloudAgent, WatcherAgent],
    tools=[
        run_windows_command,
        shell_tool,
        thinker_agent_handoff,
        coder_agent_handoff,
        docker_k8s_handoff,
        cloud_agent_handoff,
        watcher_agent_handoff,
    ],
    prompt=SUPERVISOR_PROMPT,
    add_handoff_back_messages=True,
    output_mode="last_message",
    state_schema=ReflectionState,
    middleware=[bind_context_before_model, bind_context_for_tools],
    pre_model_hook=combined_pre_model_hook
)

# Get checkpoint manager for persistence
checkpoint_manager = get_checkpoint_manager(backend="sqlite")

# Compile with checkpointing for memory persistence
supervisor = supervisor_graph.compile(
    name="deep_agent_supervisor",
    checkpointer=checkpoint_manager.get_checkpointer()
).with_config({"recursion_limit": 200})  # Increased for deep agent reflection loops

logger.info("Deep Agent Supervisor initialized with all specialized agents")
logger.info("Agents: Thinker, Coder, Builder (Docker, K8s), Cloud (AWS, Azure, GCP), Watcher")
logger.info("Features: Reflection, Error Recovery, Memory Persistence, Observability")
