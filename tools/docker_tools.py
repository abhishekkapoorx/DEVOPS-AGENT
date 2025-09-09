import os
import json
from typing import Dict, Any, List, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class CodebaseAnalysisInput(BaseModel):
    """Input for codebase analysis."""
    directory_path: str = Field(description="Path to the directory to analyze")


class CodebaseAnalysisOutput(BaseModel):
    """Output from codebase analysis."""
    languages: List[str] = Field(description="Detected programming languages")
    frameworks: List[str] = Field(description="Detected frameworks and libraries")
    dependencies: Dict[str, Any] = Field(description="Project dependencies")
    structure: Dict[str, Any] = Field(description="Project structure analysis")
    recommendations: List[str] = Field(description="Docker optimization recommendations")


def _analyze_directory(directory_path: str) -> Dict[str, Any]:
    """Perform the actual directory analysis."""
    if not os.path.exists(directory_path):
        raise ValueError(f"Directory {directory_path} does not exist")
    
    languages: List[str] = []
    frameworks: List[str] = []
    dependencies: Dict[str, Any] = {}
    structure: Dict[str, Any] = {}
    recommendations: List[str] = []
    
    # Analyze files and directories
    for root, dirs, files in os.walk(directory_path):
        # Skip hidden directories and common non-source directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv', 'env']]
        
        for file in files:
            file_path = os.path.join(root, file)
            _ = os.path.relpath(file_path, directory_path)

            # Detect programming languages
            if file.endswith('.py'):
                languages.append('Python')
            elif file.endswith('.js') or file.endswith('.ts'):
                languages.append('JavaScript/TypeScript')
            elif file.endswith('.java'):
                languages.append('Java')
            elif file.endswith('.go'):
                languages.append('Go')
            elif file.endswith('.rs'):
                languages.append('Rust')

            # Detect dependencies by reading specific files when encountered
            if file == 'requirements.txt':
                dependencies['python'] = _parse_requirements(file_path)
            elif file == 'package.json':
                dependencies['node'] = _parse_package_json(file_path)
            elif file == 'pom.xml':
                dependencies['java'] = _parse_pom_xml(file_path)
            elif file == 'go.mod':
                dependencies['go'] = _parse_go_mod(file_path)
            elif file == 'Cargo.toml':
                dependencies['rust'] = _parse_cargo_toml(file_path)

            # Detect frameworks
            if file == 'package.json':
                frameworks.extend(_detect_js_frameworks(file_path))
            elif file == 'requirements.txt':
                frameworks.extend(_detect_python_frameworks(file_path))
            elif 'Dockerfile' in file:
                recommendations.append("Existing Dockerfile found - consider optimization")
            elif 'docker-compose.yml' in file or 'docker-compose.yaml' in file:
                recommendations.append("Existing docker-compose file found")
    
    # Remove duplicates
    languages = list(set(languages))
    frameworks = list(set(frameworks))
    
    # Generate recommendations
    if 'Python' in languages:
        recommendations.extend([
            "Use multi-stage build for Python applications",
            "Consider using python:3.11-slim as base image",
            "Install only production dependencies in final stage"
        ])
    if 'JavaScript/TypeScript' in languages:
        recommendations.extend([
            "Use node:18-alpine as base image",
            "Implement multi-stage build for frontend applications",
            "Use .dockerignore to exclude node_modules"
        ])
    
    return {
        "languages": languages,
        "frameworks": frameworks,
        "dependencies": dependencies,
        "structure": structure,
        "recommendations": recommendations
    }
    
def _parse_requirements(file_path: str) -> List[str]:
    """Parse requirements.txt file."""
    try:
        with open(file_path, 'r') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except:
        return []
    
def _parse_package_json(file_path: str) -> Dict[str, Any]:
    """Parse package.json file."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except:
        return {}
    
def _parse_pom_xml(file_path: str) -> Dict[str, Any]:
    """Parse pom.xml file (simplified)."""
    return {"type": "maven", "file": file_path}
    
def _parse_go_mod(file_path: str) -> Dict[str, Any]:
    """Parse go.mod file (simplified)."""
    return {"type": "go_modules", "file": file_path}
    
def _parse_cargo_toml(file_path: str) -> Dict[str, Any]:
    """Parse Cargo.toml file (simplified)."""
    return {"type": "cargo", "file": file_path}
    
def _detect_js_frameworks(package_json_path: str) -> List[str]:
    """Detect JavaScript frameworks from package.json."""
    try:
        with open(package_json_path, 'r') as f:
            package_data = json.load(f)
            frameworks: List[str] = []
            deps = {**package_data.get('dependencies', {}), **package_data.get('devDependencies', {})}
            
            if 'react' in deps:
                frameworks.append('React')
            if 'vue' in deps:
                frameworks.append('Vue.js')
            if 'angular' in deps:
                frameworks.append('Angular')
            if 'express' in deps:
                frameworks.append('Express.js')
            if 'next' in deps:
                frameworks.append('Next.js')
            
            return frameworks
    except:
        return []
    
def _detect_python_frameworks(requirements_path: str) -> List[str]:
    """Detect Python frameworks from requirements.txt."""
    try:
        with open(requirements_path, 'r') as f:
            content = f.read().lower()
            frameworks: List[str] = []
            
            if 'django' in content:
                frameworks.append('Django')
            if 'flask' in content:
                frameworks.append('Flask')
            if 'fastapi' in content:
                frameworks.append('FastAPI')
            if 'streamlit' in content:
                frameworks.append('Streamlit')
            
            return frameworks
    except:
        return []


class DockerfileInput(BaseModel):
    """Input for Dockerfile generation."""
    analysis_result: str = Field(description="JSON string of codebase analysis results")
    output_path: str = Field(description="Path where to save the generated Dockerfile")
    optimization_level: str = Field(default="production", description="Optimization level: development, production, or minimal")


def _generate_dockerfile_with_llm(analysis: Dict[str, Any], optimization_level: str) -> str:
    """Generate Dockerfile using LLM based on analysis."""
    languages = analysis.get('languages', [])
    frameworks = analysis.get('frameworks', [])
    dependencies = analysis.get('dependencies', {})
    recommendations = analysis.get('recommendations', [])
    
    prompt = f"""
You are a Docker expert. Generate a production-ready Dockerfile based on the following codebase analysis:

**Languages Detected**: {', '.join(languages)}
**Frameworks Detected**: {', '.join(frameworks)}
**Dependencies**: {json.dumps(dependencies, indent=2)}
**Optimization Level**: {optimization_level}
**Recommendations**: {', '.join(recommendations)}

Requirements:
1. Use multi-stage builds for production optimization
2. Implement security best practices: non-root user, minimal final image, avoid extra packages
3. Avoid installing curl/wget in the final image; for health checks prefer stdlib (e.g., Python urllib) or omit if unavailable
4. Prefer up-to-date minimal bases (e.g., python:3.11-slim-bookworm, node:18-alpine) and avoid deprecated/EOL images
5. Optimize for the detected language/framework and follow best practices for layer caching
6. Include proper error handling and logging where applicable
7. Do NOT include .dockerignore content in the output. That will be created separately.

Generate ONLY the Dockerfile content, no explanations or markdown formatting.
"""
    
    # Lazy import to avoid circular dependencies at module import time
    from llms import openai_models
    model = openai_models["gpt-4o-mini"]
    response = model.invoke(prompt)
    content = response.content.strip()
    return _strip_dockerignore_from_dockerfile(content)
    

def _strip_dockerignore_from_dockerfile(content: str) -> str:
    """Remove any mistakenly included .dockerignore lines from Dockerfile content."""
    lines = content.splitlines()
    cleaned: List[str] = []
    for line in lines:
        # If the model included a section marker, stop there
        if line.strip().lower().startswith('# .dockerignore'):
            break
        # Heuristic: ignore obvious dockerignore patterns when they appear standalone
        if line.strip() in {
            '*.pyc', '*.pyo', '__pycache__/', 'env/', 'venv/', '.venv/', '.test/', '.git/', '*.log', '*.egg-info/',
            'node_modules/', '.next/', 'dist/', 'build/', 'coverage/', '.pytest_cache/', '.mypy_cache/', '.idea/', '.vscode/',
        }:
            continue
        cleaned.append(line)
    return "\n".join(cleaned).rstrip() + "\n"


class DockerComposeInput(BaseModel):
    """Input for Docker Compose generation."""
    analysis_result: str = Field(description="JSON string of codebase analysis results")
    output_path: str = Field(description="Path where to save the generated docker-compose.yml")
    environment: str = Field(default="development", description="Environment: development, staging, or production")
    services: List[str] = Field(default=[], description="Additional services to include (e.g., postgres, redis, nginx)")


def _get_python_service(environment: str) -> Dict[str, Any]:
    """Get Python service configuration."""
    if environment == "production":
        return {
            "build": ".",
            "ports": ["8000:8000"],
            "environment": ["ENV=production"],
            "depends_on": ["db"],
            "restart": "unless-stopped"
        }
    else:
        return {
            "build": ".",
            "ports": ["8000:8000"],
            "volumes": [".:/app", "/app/venv"],
            "environment": ["ENV=development"],
            "depends_on": ["db"]
        }

def _get_node_service(environment: str) -> Dict[str, Any]:
    """Get Node.js service configuration."""
    if environment == "production":
        return {
            "build": ".",
            "ports": ["3000:3000"],
            "environment": ["NODE_ENV=production"],
            "restart": "unless-stopped"
        }
    else:
        return {
            "build": ".",
            "ports": ["3000:3000"],
            "volumes": [".:/app", "/app/node_modules"],
            "environment": ["NODE_ENV=development"]
        }

def _get_java_service(environment: str) -> Dict[str, Any]:
    """Get Java service configuration."""
    return {
        "build": ".",
        "ports": ["8080:8080"],
        "environment": [f"SPRING_PROFILES_ACTIVE={environment}"],
        "depends_on": ["db"],
        "restart": "unless-stopped"
    }

def _get_go_service(environment: str) -> Dict[str, Any]:
    """Get Go service configuration."""
    return {
        "build": ".",
        "ports": ["8080:8080"],
        "environment": [f"ENV={environment}"],
        "restart": "unless-stopped"
    }

def _get_generic_service(environment: str) -> Dict[str, Any]:
    """Get generic service configuration."""
    return {
        "build": ".",
        "ports": ["8080:8080"],
        "environment": [f"ENV={environment}"]
    }

def _get_postgres_service(environment: str) -> Dict[str, Any]:
    """Get PostgreSQL service configuration."""
    return {
        "image": "postgres:15-alpine",
        "environment": {
            "POSTGRES_DB": "appdb",
            "POSTGRES_USER": "appuser",
            "POSTGRES_PASSWORD": "apppass"
        },
        "volumes": ["postgres_data:/var/lib/postgresql/data"],
        "ports": ["5432:5432"]
    }

def _get_redis_service(environment: str) -> Dict[str, Any]:
    """Get Redis service configuration."""
    return {
        "image": "redis:7-alpine",
        "ports": ["6379:6379"],
        "command": "redis-server --appendonly yes",
        "volumes": ["redis_data:/data"]
    }

def _get_nginx_service(environment: str) -> Dict[str, Any]:
    """Get Nginx service configuration."""
    return {
        "image": "nginx:alpine",
        "ports": ["80:80", "443:443"],
        "volumes": ["./nginx.conf:/etc/nginx/nginx.conf"],
        "depends_on": ["app"]
    }

def _get_mongodb_service(environment: str) -> Dict[str, Any]:
    """Get MongoDB service configuration."""
    return {
        "image": "mongo:6",
        "environment": {
            "MONGO_INITDB_ROOT_USERNAME": "admin",
            "MONGO_INITDB_ROOT_PASSWORD": "password"
        },
        "volumes": ["mongodb_data:/data/db"],
        "ports": ["27017:27017"]
    }

def _get_frontend_service(environment: str) -> Dict[str, Any]:
    """Get frontend service configuration."""
    return {
        "build": {
            "context": "./frontend",
            "dockerfile": "Dockerfile"
        },
        "ports": ["3000:3000"],
        "environment": [f"NODE_ENV={environment}"]
    }

def _generate_compose_content(analysis: Dict[str, Any], environment: str, additional_services: List[str]) -> str:
    """Generate docker-compose.yml content."""
    languages = analysis.get('languages', [])
    frameworks = analysis.get('frameworks', [])
    
    # Base services
    services: Dict[str, Any] = {}
    
    # Main application service
    if 'Python' in languages:
        services['app'] = _get_python_service(environment)
    elif 'JavaScript/TypeScript' in languages:
        services['app'] = _get_node_service(environment)
    elif 'Java' in languages:
        services['app'] = _get_java_service(environment)
    elif 'Go' in languages:
        services['app'] = _get_go_service(environment)
    else:
        services['app'] = _get_generic_service(environment)
    
    # Add database services based on frameworks
    if 'Django' in frameworks or 'Flask' in frameworks:
        services['db'] = _get_postgres_service(environment)
    elif 'React' in frameworks or 'Vue.js' in frameworks:
        services['frontend'] = _get_frontend_service(environment)
    
    # Add additional services
    for service in additional_services:
        if service.lower() == 'postgres':
            services['postgres'] = _get_postgres_service(environment)
        elif service.lower() == 'redis':
            services['redis'] = _get_redis_service(environment)
        elif service.lower() == 'nginx':
            services['nginx'] = _get_nginx_service(environment)
        elif service.lower() == 'mongodb':
            services['mongodb'] = _get_mongodb_service(environment)
    
    # Generate compose content
    compose_content = f"""version: '3.8'

services:
"""
    
    for service_name, service_config in services.items():
        compose_content += f"  {service_name}:\n"
        for key, value in service_config.items():
            if isinstance(value, dict):
                compose_content += f"    {key}:\n"
                for sub_key, sub_value in value.items():
                    compose_content += f"      {sub_key}: {sub_value}\n"
            elif isinstance(value, list):
                compose_content += f"    {key}:\n"
                for item in value:
                    compose_content += f"      - {item}\n"
            else:
                compose_content += f"    {key}: {value}\n"
        compose_content += "\n"
    
    # Add networks and volumes if needed
    if any('db' in service or 'postgres' in service or 'mongodb' in service for service in services.keys()):
        compose_content += """networks:
  default:
    driver: bridge

volumes:
  postgres_data:
  mongodb_data:
"""
    
    return compose_content

@tool("analyze_codebase", args_schema=CodebaseAnalysisInput)
def analyze_codebase(directory_path: str) -> str:
    """Analyze a codebase to detect languages, frameworks, dependencies, and recommendations."""
    try:
        analysis = _analyze_directory(directory_path)
        return json.dumps(analysis, indent=2)
    except Exception as e:
        return f"Error analyzing codebase: {str(e)}"

@tool("generate_dockerfile", args_schema=DockerfileInput)
def generate_dockerfile(analysis_result: str, output_path: str, optimization_level: str = "production") -> str:
    """Generate a production-ready Dockerfile based on codebase analysis results."""
    try:
        analysis = json.loads(analysis_result)
        dockerfile_content = _generate_dockerfile_with_llm(analysis, optimization_level)
        with open(output_path, 'w') as f:
            f.write(dockerfile_content)
        return f"Dockerfile generated successfully at {output_path}"
    except Exception as e:
        return f"Error generating Dockerfile: {str(e)}"

@tool("generate_docker_compose", args_schema=DockerComposeInput)
def generate_docker_compose(analysis_result: str, output_path: str, environment: str = "development", services: Optional[List[str]] = None) -> str:
    """Generate a docker-compose.yml file based on codebase analysis results."""
    try:
        if services is None:
            services = []
        analysis = json.loads(analysis_result)
        compose_content = _generate_compose_content(analysis, environment, services)
        with open(output_path, 'w') as f:
            f.write(compose_content)
        return f"docker-compose.yml generated successfully at {output_path}"
    except Exception as e:
        return f"Error generating docker-compose.yml: {str(e)}"
