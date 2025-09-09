# Tools Directory

This directory contains modular tools for the agentic deployment system. Each tool is designed to be reusable and follows LangChain's BaseTool interface.

## Structure

```
tools/
├── __init__.py          # Exports all available tools
├── docker_tools.py      # Docker-related tools
├── k8s_tools.py         # Kubernetes-related tools
└── README.md           # This documentation
```

## Available Tools

### Docker Tools (`docker_tools.py`)

#### 1. CodebaseAnalyzer
**Purpose**: Analyzes codebases to detect programming languages, frameworks, dependencies, and project structure.

**Features**:
- Detects programming languages (Python, JavaScript/TypeScript, Java, Go, Rust)
- Identifies frameworks (React, Vue, Django, Flask, etc.)
- Parses dependency files (requirements.txt, package.json, pom.xml, etc.)
- Provides Docker optimization recommendations
- Skips common non-source directories (node_modules, __pycache__, etc.)

**Usage**:
```python
from tools import CodebaseAnalyzer

analyzer = CodebaseAnalyzer()
result = analyzer._run("/path/to/project")
```

#### 2. DockerfileGenerator
**Purpose**: Generates optimized Dockerfiles based on codebase analysis results.

**Features**:
- Multi-stage builds for production optimization
- Language-specific optimizations (Python, Node.js, Java, Go)
- Security best practices (non-root users, minimal base images)
- Health checks and proper port exposure
- Support for different optimization levels (development, production, minimal)

**Usage**:
```python
from tools import DockerfileGenerator

generator = DockerfileGenerator()
result = generator._run(
    analysis_result=analysis_json,
    output_path="./Dockerfile",
    optimization_level="production"
)
```

#### 3. DockerComposeGenerator
**Purpose**: Creates docker-compose.yml files for different environments and service configurations.

**Features**:
- Environment-specific configurations (development, staging, production)
- Automatic service detection based on frameworks
- Support for common services (PostgreSQL, Redis, MongoDB, Nginx)
- Proper networking and volume management
- Health checks and restart policies

**Usage**:
```python
from tools import DockerComposeGenerator

generator = DockerComposeGenerator()
result = generator._run(
    analysis_result=analysis_json,
    output_path="./docker-compose.yml",
    environment="development",
    services=["postgres", "redis"]
)
```

## Tool Design Principles

### 1. Modularity
Each tool is self-contained and can be used independently or in combination with other tools.

### 2. LangChain Integration
All tools inherit from `langchain_core.tools.BaseTool` and follow LangChain conventions:
- Proper input/output schemas using Pydantic
- Clear descriptions for LLM understanding
- Structured error handling

### 3. Extensibility
Tools are designed to be easily extended:
- Add new language support to CodebaseAnalyzer
- Create new optimization strategies for DockerfileGenerator
- Add more services to DockerComposeGenerator

### 4. Best Practices
- Security-first approach (non-root users, minimal images)
- Performance optimization (multi-stage builds, layer caching)
- Production-ready configurations
- Comprehensive error handling

## Adding New Tools

To add a new tool:

1. Create a new class inheriting from `BaseTool`
2. Define input/output schemas using Pydantic
3. Implement the `_run` method with proper error handling
4. Add the tool to `__init__.py` exports
5. Update this README with documentation

Example:
```python
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

class MyToolInput(BaseModel):
    param1: str = Field(description="Description of param1")

class MyTool(BaseTool):
    name = "my_tool"
    description = "Description of what this tool does"
    args_schema = MyToolInput
    
    def _run(self, param1: str) -> str:
        # Implementation here
        return "Result"
```

## Dependencies

The tools require the following packages:
- `langchain-core` - Base tool interface
- `pydantic` - Input/output validation
- `json` - JSON handling
- `os` - File system operations

### Kubernetes Tools (`k8s_tools.py`)

#### 1. ManifestGenerator
**Purpose**: Generates comprehensive Kubernetes manifests including Deployments, Services, ConfigMaps, Ingress, and HPA.

**Features**:
- Complete Kubernetes manifest generation (Deployments, Services, ConfigMaps, Ingress, HPA)
- Production-ready configurations with security best practices
- Resource management and auto-scaling setup
- Health checks and probes configuration
- Environment-specific customizations
- Proper labeling and selectors

**Usage**:
```python
from tools import ManifestGenerator

generator = ManifestGenerator()
result = generator._run(
    app_name="my-app",
    app_type="web",
    image="my-app:latest",
    port=8080,
    replicas=3,
    environment="production",
    output_dir="./k8s"
)
```

#### 2. HelmChartGenerator
**Purpose**: Creates comprehensive Helm charts with templates, values, and Chart.yaml for application deployment.

**Features**:
- Complete Helm chart structure with templates
- Configurable values.yaml with sensible defaults
- Deployment, Service, Ingress, and HPA templates
- Security contexts and resource management
- Auto-scaling and monitoring configurations
- Customizable values and overrides

**Usage**:
```python
from tools import HelmChartGenerator

generator = HelmChartGenerator()
result = generator._run(
    app_name="my-app",
    app_type="api",
    image="my-app:v1.0.0",
    port=3000,
    replicas=2,
    environment="staging",
    output_dir="./helm-charts"
)
```

#### 3. ServiceGenerator
**Purpose**: Generates individual Kubernetes Service manifests for specific service configurations.

**Features**:
- Various service types (ClusterIP, NodePort, LoadBalancer)
- Proper port mapping and protocol configuration
- Label-based service discovery
- Custom selector configurations

**Usage**:
```python
from tools import ServiceGenerator

generator = ServiceGenerator()
result = generator._run(
    service_name="my-service",
    service_type="LoadBalancer",
    port=80,
    target_port=8080,
    selector={"app": "my-app"},
    output_path="./service.yaml"
)
```

## Examples

See `examples/docker_agent_usage.py` for complete usage examples of all Docker tools.
