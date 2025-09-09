from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, START, END
from typing import Annotated, List, Dict, Any
from typing_extensions import TypedDict
from langchain_community.agent_toolkits.file_management.toolkit import FileManagementToolkit
import os
import json
import asyncio

from llms import openai_models, groq_models, gemini_models
from tools import analyze_codebase, generate_dockerfile, generate_docker_compose
from utils import _sanitize_path, _get_project_root_from_env

# States


class DockerAgent(TypedDict):
    messages: Annotated[List[str], add_messages]
    analysis_result: str
    dockerfile_content: str
    compose_content: str
    user_requirements: str
    output_directory: str
    project_root: str



# Tools
# Avoid blocking os.getcwd by preferring PROJECT_ROOT env or '.'
# root_dir = os.getenv("PROJECT_ROOT") or "."
root_dir = r"C:\Users\Raghav Singla\Desktop\linux\pbl-agentic-deployment"
file_tools = FileManagementToolkit(root_dir=root_dir).get_tools()

docker_tools = [
    analyze_codebase,
    generate_dockerfile,
    generate_docker_compose,
]

all_tools = file_tools + docker_tools

# Initialize LLM
model = openai_models["gpt-4o-mini"]

# Node Functions


async def analyze_codebase_node(state: DockerAgent) -> DockerAgent:
    """Analyze the codebase to understand the project structure."""
    last_message = state["messages"][-1] if state["messages"] else ""

    # Determine project root and directory to analyze
    project_root = _sanitize_path(state.get("project_root", _get_project_root_from_env()))
    directory_path = state.get("output_directory", project_root)
    if directory_path in (".", "./", ""):
        directory_path = project_root
    elif not os.path.isabs(directory_path):
        directory_path = os.path.join(project_root, directory_path)
    directory_path = _sanitize_path(directory_path)

    # Use the analyze_codebase tool function (async)
    analysis_result = await analyze_codebase.ainvoke({"directory_path": directory_path})

    # Create response message and return updated state
    response = f"""I've analyzed your codebase. Here's what I found:

{analysis_result}

Based on this analysis, I'll now generate optimized Docker configurations for your project."""

    return {"messages": [AIMessage(content=response)], "analysis_result": analysis_result}


async def generate_dockerfile_node(state: DockerAgent) -> DockerAgent:
    """Generate Dockerfile using LLM based on analysis."""
    analysis_result = state.get("analysis_result", "{}")
    user_requirements = state.get("user_requirements", "")
    project_root = _sanitize_path(state.get("project_root", _get_project_root_from_env()))
    output_dir = state.get("output_directory", project_root)
    if output_dir in (".", "./", ""):
        output_dir = project_root
    elif not os.path.isabs(output_dir):
        output_dir = os.path.join(project_root, output_dir)
    output_dir = _sanitize_path(output_dir)

    # Create LLM prompt for Dockerfile generation
    prompt = f"""
You are a Docker expert. Generate a production-ready Dockerfile based on the following information:

**Codebase Analysis:**
{analysis_result}

**User Requirements:**
{user_requirements}

**Requirements:**
1. Use multi-stage builds for production optimization
2. Implement security best practices: non-root user, minimal final image, drop unnecessary packages
3. Avoid installing curl/wget in the final image; for health checks, prefer runtime stdlib (e.g., Python urllib) or omit if none available
4. Prefer up-to-date minimal bases (e.g., python:3.11-slim-bookworm or distroless where feasible); do not use deprecated/EOL images
5. Optimize for the detected language/framework and follow best practices for layer caching
6. Include proper error handling and logging where applicable
7. Do NOT include .dockerignore content; it will be created separately
8. Optimize for the specified environment

Generate ONLY the Dockerfile content, no explanations or markdown formatting. Make it production-ready and secure.
"""

    try:
        response = await model.ainvoke(prompt)
        dockerfile_content = response.content.strip()

        # Save Dockerfile (offload blocking I/O)
        dockerfile_path = os.path.join(output_dir, "Dockerfile")
        await asyncio.to_thread(_write_text_file, dockerfile_path, dockerfile_content)

        # Also generate a .dockerignore based on analysis
        dockerignore_path = os.path.join(output_dir, ".dockerignore")
        dockerignore_content = _generate_dockerignore_from_analysis(analysis_result)
        try:
            await asyncio.to_thread(_write_text_file, dockerignore_path, dockerignore_content)
        except Exception:
            pass

        response_msg = f"""I've generated a production-ready Dockerfile for your project:

```dockerfile
{dockerfile_content}
```

The Dockerfile has been saved to: {dockerfile_path}
Also created .dockerignore at: {dockerignore_path}

Key features implemented:
- Multi-stage build for optimization
- Security best practices (non-root user)
- Health checks and proper port exposure
- Optimized for your detected technology stack
- Production-ready configuration"""

        return {"messages": [AIMessage(content=response_msg)], "dockerfile_content": dockerfile_content}

    except Exception as e:
        error_msg = f"Error generating Dockerfile: {str(e)}"
        return {"messages": [AIMessage(content=error_msg)]}


async def generate_compose_node(state: DockerAgent) -> DockerAgent:
    """Generate docker-compose.yml using LLM based on analysis."""
    analysis_result = state.get("analysis_result", "{}")
    dockerfile_content = state.get("dockerfile_content", "")
    user_requirements = state.get("user_requirements", "")
    project_root = _sanitize_path(state.get("project_root", _get_project_root_from_env()))
    output_dir = state.get("output_directory", project_root)
    if output_dir in (".", "./", ""):
        output_dir = project_root
    elif not os.path.isabs(output_dir):
        output_dir = os.path.join(project_root, output_dir)
    output_dir = _sanitize_path(output_dir)

    # Create LLM prompt for docker-compose generation
    prompt = f"""
You are a Docker Compose expert. Generate a production-ready docker-compose.yml file based on the following information:

**Codebase Analysis:**
{analysis_result}

**Generated Dockerfile:**
{dockerfile_content}

**User Requirements:**
{user_requirements}

**Requirements:**
1. Create appropriate services for the application
2. Include necessary databases and dependencies
3. Configure proper networking and volumes
4. Set up environment variables
5. Include health checks and restart policies
6. Optimize for production deployment
7. Include development and production configurations
8. Add proper service dependencies

Generate ONLY the docker-compose.yml content, no explanations or markdown formatting. Make it production-ready.
"""

    try:
        response = await model.ainvoke(prompt)
        compose_content = response.content.strip()

        # Save docker-compose.yml (offload blocking I/O)
        compose_path = os.path.join(output_dir, "docker-compose.yml")
        await asyncio.to_thread(_write_text_file, compose_path, compose_content)

        response_msg = f"""I've generated a comprehensive docker-compose.yml file for your project:

```yaml
{compose_content}
```

The docker-compose.yml has been saved to: {compose_path}

Key features implemented:
- Multi-service architecture
- Proper networking and volumes
- Environment variable configuration
- Health checks and restart policies
- Production-ready configuration
- Service dependencies and ordering"""

        return {"messages": [AIMessage(content=response_msg)], "compose_content": compose_content}

    except Exception as e:
        error_msg = f"Error generating docker-compose.yml: {str(e)}"
        return {"messages": [AIMessage(content=error_msg)]}


async def review_and_optimize_node(state: DockerAgent) -> DockerAgent:
    """Review and provide optimization recommendations."""
    analysis_result = state.get("analysis_result", "{}")
    dockerfile_content = state.get("dockerfile_content", "")
    compose_content = state.get("compose_content", "")

    # Create LLM prompt for review and optimization
    prompt = f"""
You are a Docker expert reviewer. Review the following Docker configurations and provide optimization recommendations:

**Codebase Analysis:**
{analysis_result}

**Generated Dockerfile:**
{dockerfile_content}

**Generated docker-compose.yml:**
{compose_content}

**Review Requirements:**
1. Check for security vulnerabilities
2. Identify performance optimization opportunities
3. Suggest best practices improvements
4. Recommend monitoring and logging setup
5. Provide deployment instructions
6. Suggest .dockerignore file content
7. Recommend CI/CD integration steps

Provide a comprehensive review with specific recommendations and improvements.
"""

    try:
        response = await model.ainvoke(prompt)
        review_content = response.content.strip()

        response_msg = f"""## Docker Configuration Review & Optimization

{review_content}

## Next Steps:
1. Review the generated files in your output directory
2. Test the configurations with `docker-compose up --build`
3. Implement the suggested optimizations
4. Set up monitoring and logging as recommended
5. Integrate with your CI/CD pipeline

Your Docker setup is now ready for production deployment!"""

        return {"messages": [AIMessage(content=response_msg)]}

    except Exception as e:
        error_msg = f"Error during review: {str(e)}"
        return {"messages": [AIMessage(content=error_msg)]}


def should_continue(state: DockerAgent) -> str:
    """Determine the next step in the workflow."""
    messages = state["messages"]
    last_message = messages[-1] if messages else ""

    # Check if we have analysis result
    if not state.get("analysis_result"):
        return "analyze"

    # Check if we have dockerfile content
    if not state.get("dockerfile_content"):
        return "dockerfile"

    # Check if we have compose content
    if not state.get("compose_content"):
        return "compose"

    # All done, proceed to review
    return "review"


# Graph
graph = StateGraph(DockerAgent, input_schema=DockerAgent,
                   output_schema=DockerAgent)

# Add nodes
graph.add_node("analyze", analyze_codebase_node)
graph.add_node("dockerfile", generate_dockerfile_node)
graph.add_node("compose", generate_compose_node)
graph.add_node("review", review_and_optimize_node)

# Add edges
graph.add_edge(START, "analyze")
graph.add_conditional_edges("analyze", should_continue, {
    "dockerfile": "dockerfile",
    "compose": "compose",
    "review": "review"
})
graph.add_conditional_edges("dockerfile", should_continue, {
    "compose": "compose",
    "review": "review"
})
graph.add_conditional_edges("compose", should_continue, {
    "review": "review"
})
graph.add_edge("review", END)

agent = graph.compile(name="docker_agent")


def _generate_dockerignore_from_analysis(analysis_json: str) -> str:
    """Generate a reasonable .dockerignore from analysis results."""
    # Base ignores common to most projects
    patterns = [
        "__pycache__/",
        "*.pyc",
        "*.pyo",
        "*.pyd",
        "*.log",
        ".pytest_cache/",
        ".mypy_cache/",
        "env/",
        "venv/",
        ".venv/",
        "node_modules/",
        ".git/",
        ".DS_Store",
        "dist/",
        "build/",
        "coverage/",
        "*.egg-info/",
    ]
    try:
        data = json.loads(analysis_json or "{}")
        languages = set(data.get("languages", []))
        frameworks = set(data.get("frameworks", []))
        # Language-specific ignores
        if "JavaScript/TypeScript" in languages:
            patterns.extend([".next/", "out/", "*.map"])
        if "Java" in languages:
            patterns.extend(["target/"])
        if "Go" in languages:
            patterns.extend(["bin/", "*.test"])
    except Exception:
        pass
    # Deduplicate while preserving order
    seen = set()
    ordered = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return "\n".join(ordered) + "\n"


def _write_text_file(path: str, content: str) -> None:
    """Write text to file (blocking). Use via asyncio.to_thread to avoid blocking the event loop."""
    with open(path, 'w') as f:
        f.write(content)
