Abstract

This report documents the design, development, and capabilities of an agentic deployment system that automates building, containerizing, and deploying applications across major cloud providers. The project combines specialized agents (Builder, Cloud, Coder, Thinker) with a codebase indexing and semantic search engine, and provides a VS Code extension for interactive control. It delivers repeatable infrastructure automation for Docker and Kubernetes, cloud provisioning for AWS/Azure/GCP, and first-class developer ergonomics via tools and tests. The system employs a planning-driven approach where each step involves careful planning before execution.

Introduction															

Modern software teams increasingly rely on automation to reduce deployment risk and accelerate delivery. This project, `pbl-agentic-deployment`, explores an agentic architecture where narrowly-scoped agents collaborate to perform build, packaging, and cloud deployment tasks. The system integrates:
- Agent orchestration and cloud-specific executors
- Codebase indexing for semantic understanding of large repositories
- Developer tooling via a VS Code extension and CLI
- A test suite to ensure reliability and fast iteration

Objective

The primary objectives are:
- Automate end-to-end build and deployment workflows for applications
- Provide cloud-agnostic abstractions with provider-specific implementations (AWS, Azure, GCP)
- Enable semantic code search to guide agent actions and improve explainability
- Offer a developer-friendly interface (extension/CLI) to supervise, inspect, and trigger agent tasks
- Ensure reproducibility through tests and clear configuration

Technology Stack

- Programming Language: Python 3.11
- Agent Framework: Custom agents under `agents/` with role specialization
- Containerization & Orchestration: Docker, Kubernetes (tools in `tools/` and `agents/BuilderAgent/`)
- Cloud Providers: AWS, Azure, GCP (implementations in `agents/CloudAgent/`)
- Code Understanding: Semantic indexing and search (`codebase_indexing/`)
- IDE Integration: VS Code extension (TypeScript/React in `extension/`)
- LLM Connectors: OpenAI, Groq, Gemini, Ollama (`llms/`)
- Testing: Pytest-based suite under `tests/`

Project Description														

At the core, the system defines specialized agents:
- ThinkerAgent: Plans multi-step tasks and breaks down goals
- CoderAgent: Generates or edits code guided by index/search
- BuilderAgent: Builds artifacts, creates Docker images, and prepares K8s manifests
- CloudAgent: Provisions and deploys to cloud targets (AWS, Azure, GCP)

These agents collaborate through orchestrated prompts and tool usage to take a repository from source to a deployed service. A key feature of the system is its planning-driven approach: at each step of the workflow, the system performs planning to determine the optimal actions before execution. This ensures that each operation is well-thought-out and contextually appropriate. The `codebase_indexing` package provides parsers, an indexer, and a search engine to answer questions like "where is deployment configured?" or "how is authentication handled?" which the agents use to make informed changes. The VS Code extension adds a chat-driven UI to trigger operations, inspect sessions, and view output.

Key Project Phases and Development Lifecycle	

1. Discovery & Indexing
   - Parse and index the repository across multiple languages
   - Enable semantic retrieval for agent reasoning
   - Planning phase determines indexing strategy and scope
2. Planning & Authoring
   - ThinkerAgent proposes steps; CoderAgent makes targeted edits
   - Each code change is preceded by planning to assess impact and approach
3. Build & Packaging
   - BuilderAgent compiles/builds, produces Docker images, and validates manifests
   - Planning occurs before build steps to determine optimal build strategy
4. Provisioning & Deployment
   - CloudAgent applies provider-specific steps for AWS/Azure/GCP
   - Tools in `tools/` handle Docker/K8s interactions
   - Planning is performed at each deployment step to ensure correct resource allocation and configuration
5. Verification & Monitoring
   - Tests validate workflows and deployment success
   - Planning guides verification strategy and test selection
6. Iteration
   - Failures feed back into planning; index helps pinpoint fixes quickly
   - Each iteration includes a planning phase to refine the approach

System Architecture & Design											

Design principles:
- Single-responsibility agents with clear boundaries
- Cloud abstraction layer with provider specializations
- Deterministic operations via CLI/tools and idempotent steps
- Treat the codebase as a knowledge graph via indexing/search
- Developer-first UX with an integrated extension

Core components:
- `agents/` – Role-based agents and cloud implementations
- `codebase_indexing/` – Indexer, parsers (tree-sitter backed), search engine, query builder
- `tools/` – Docker/K8s command tools and terminal integration
- `extension/` – VS Code extension for chat-driven supervision
- `llms/` – Provider clients for model-backed reasoning
- `tests/` – Contract and integration tests for reliability

High-Level System Architecture

Data flow (conceptual):
1. Developer triggers an operation via CLI/extension
2. Planning phase: ThinkerAgent plans the overall strategy; Codebase Indexing answers context queries
3. Planning before coding: CoderAgent plans edits, then executes code/manifest changes
4. Planning before building: BuilderAgent plans build strategy, then builds images/manifests
5. Planning before deployment: CloudAgent plans deployment steps, then deploys to target (AWS/Azure/GCP) using Docker/K8s tools
6. Each step includes continuous planning to adapt to changing conditions and ensure optimal execution

Features Implemented	

- Multi-cloud deployment agents: `AWSAgent`, `AzureAgent`, `GCPAgent`
- Builder utilities for Docker and Kubernetes in `agents/BuilderAgent/` and `tools/`
- Semantic indexing and search with language-specific parsers
- VS Code extension providing chat UI, session management, and chat message components
- Pluggable LLM providers: OpenAI, Groq, Gemini, and local models via Ollama
- Test suite: quick sanity tests, CLI tests, and search/index loading tests

Challenges Faced														

- Provider variance: Normalizing AWS/Azure/GCP workflows while retaining provider strengths
- State management: Coordinating multi-agent state and avoiding conflicting actions
- Observability: Making agent decisions explainable via logs and search context
- Security & credentials: Managing secrets across clouds and local dev smoothly
- Determinism: Ensuring repeatable builds and deployments across environments

Conclusion

The project demonstrates a practical, extensible agentic approach to software deployment. By combining specialized agents, semantic code understanding, and ergonomic tooling, teams can achieve faster, safer delivery across multiple clouds. Future work includes deeper policy-as-code integration, richer drift detection, more comprehensive e2e tests, and expanded provider support. The foundation laid here supports iterative growth while delivering immediate value to developer workflows.