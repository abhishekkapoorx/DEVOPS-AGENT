from langgraph_supervisor.handoff import create_handoff_tool

# Docker Agent handoff tool
docker_agent_handoff = create_handoff_tool(
    agent_name="docker_agent",
    name="docker_agent",
    description="""
    Handoff to Docker Agent for containerization and Docker-related tasks.

    Scope:
    - Codebase analysis for language/framework detection
    - Dockerfile generation with multi-stage builds
    - Docker Compose configuration for development/production
    - Container optimization for security and performance
    - Image size reduction and layer optimization
    - Container networking and volume management
    - Docker security hardening and best practices
    - Container registry management and image tagging

    Behavior:
    - Analyzes codebases autonomously to detect technologies
    - Generates production-ready container configurations
    - Implements security best practices and optimizations
    - Provides detailed explanations of generated configurations
    - No manual user intervention required
    """
)

# Kubernetes Agent handoff tool
k8s_agent_handoff = create_handoff_tool(
    agent_name="k8s_agent",
    name="k8s_agent",
    description="""
    Handoff to Kubernetes Agent for orchestration and cluster management.

    Scope:
    - Kubernetes manifest generation (Deployments, Services, ConfigMaps)
    - Helm chart creation and customization
    - Ingress controllers and load balancer configuration
    - Monitoring setup with Prometheus/Grafana
    - Auto-scaling policies and resource management
    - Secrets management and RBAC configurations
    - Cluster security and network policies
    - Troubleshooting and performance optimization

    Behavior:
    - Generates production-ready Kubernetes configurations
    - Implements monitoring and observability best practices
    - Configures security policies and access controls
    - Provides detailed explanations of generated manifests
    - No manual user intervention required
    """
)