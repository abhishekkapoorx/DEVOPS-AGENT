from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, START, END
from typing import Annotated, List, TypedDict, Dict, Any
from langchain_community.agent_toolkits.file_management.toolkit import FileManagementToolkit
import os
import json

from llms import openai_models, groq_models, gemini_models
from tools import ManifestGenerator, HelmChartGenerator, ServiceGenerator

# States
class K8sAgent(TypedDict):
	messages: Annotated[List[str], add_messages]
	app_requirements: str
	manifests_content: str
	helm_chart_content: str
	user_requirements: str
	output_directory: str

# Tools
root_dir = os.getcwd()
file_tools = FileManagementToolkit(root_dir=root_dir).get_tools()

k8s_tools = [
    ManifestGenerator(),
    HelmChartGenerator(),
    ServiceGenerator()
]

all_tools = file_tools + k8s_tools

# Initialize LLM
model = openai_models["gpt-4o-mini"]

# Node Functions
def analyze_requirements_node(state: K8sAgent) -> K8sAgent:
	"""Analyze user requirements for Kubernetes deployment."""
	last_message = state["messages"][-1] if state["messages"] else ""
	user_requirements = last_message.content if hasattr(last_message, 'content') else str(last_message)
	
	# Store requirements in state
	state["user_requirements"] = user_requirements
	
	# Create LLM prompt to analyze requirements
	prompt = f"""
You are a Kubernetes expert. Analyze the following user requirements and extract key information for Kubernetes deployment:

**User Requirements:**
{user_requirements}

**Extract and provide:**
1. Application type (web, api, database, microservice, etc.)
2. Expected traffic and scaling requirements
3. Resource requirements (CPU, memory)
4. Environment (development, staging, production)
5. Dependencies (databases, external services)
6. Security requirements
7. Monitoring and logging needs
8. Deployment preferences (manifests vs Helm charts)

Provide a structured analysis in JSON format.
"""
	
	try:
		response = model.invoke(prompt)
		analysis = response.content.strip()
		state["app_requirements"] = analysis
		
		response_msg = f"""I've analyzed your requirements for Kubernetes deployment:

{analysis}

Based on this analysis, I'll now generate the appropriate Kubernetes configurations for your application."""
		
		return {"messages": [AIMessage(content=response_msg)]}
		
	except Exception as e:
		error_msg = f"Error analyzing requirements: {str(e)}"
		return {"messages": [AIMessage(content=error_msg)]}

def generate_manifests_node(state: K8sAgent) -> K8sAgent:
	"""Generate Kubernetes manifests using LLM."""
	app_requirements = state.get("app_requirements", "{}")
	user_requirements = state.get("user_requirements", "")
	output_dir = state.get("output_directory", "./k8s")
	
	# Create LLM prompt for manifest generation
	prompt = f"""
You are a Kubernetes expert. Generate comprehensive Kubernetes manifests based on the following requirements:

**Application Requirements Analysis:**
{app_requirements}

**User Requirements:**
{user_requirements}

**Generate the following manifests:**
1. Deployment with proper resource limits, health checks, and security contexts
2. Service for internal communication
3. ConfigMap for configuration management
4. Ingress for external access
5. HorizontalPodAutoscaler for auto-scaling
6. ServiceAccount with minimal permissions
7. NetworkPolicy for security (if needed)

**Requirements:**
- Use production-ready configurations
- Implement security best practices
- Include proper resource requests and limits
- Add health checks and probes
- Use non-root users and read-only filesystems
- Implement proper labeling and selectors
- Configure auto-scaling appropriately
- Include monitoring and logging annotations

Generate each manifest as a separate YAML block with clear headers. Make them production-ready and secure.
"""
	
	try:
		response = model.invoke(prompt)
		manifests_content = response.content.strip()
		
		# Save manifests to files
		os.makedirs(output_dir, exist_ok=True)
		
		# Parse and save individual manifests
		manifests = manifests_content.split('---')
		manifest_files = []
		
		for i, manifest in enumerate(manifests):
			if manifest.strip():
				# Extract kind from manifest
				lines = manifest.strip().split('\n')
				kind = "unknown"
				name = f"manifest-{i}"
				
				for line in lines:
					if line.strip().startswith('kind:'):
						kind = line.split(':')[1].strip()
					elif line.strip().startswith('name:'):
						name = line.split(':')[1].strip()
				
				filename = f"{name}-{kind.lower()}.yaml"
				filepath = os.path.join(output_dir, filename)
				
				with open(filepath, 'w') as f:
					f.write(manifest.strip())
				
				manifest_files.append(filepath)
		
		state["manifests_content"] = manifests_content
		
		response_msg = f"""I've generated comprehensive Kubernetes manifests for your application:

{manifests_content}

**Generated files:**
{chr(10).join(f"- {f}" for f in manifest_files)}

**Key features implemented:**
- Production-ready deployment with security contexts
- Auto-scaling with HPA
- Proper resource management
- Health checks and probes
- Network policies for security
- Service account with minimal permissions
- Ingress configuration for external access"""
		
		return {"messages": [AIMessage(content=response_msg)]}
		
	except Exception as e:
		error_msg = f"Error generating manifests: {str(e)}"
		return {"messages": [AIMessage(content=error_msg)]}

def generate_helm_chart_node(state: K8sAgent) -> K8sAgent:
	"""Generate Helm chart using LLM."""
	app_requirements = state.get("app_requirements", "{}")
	manifests_content = state.get("manifests_content", "")
	user_requirements = state.get("user_requirements", "")
	output_dir = state.get("output_directory", "./helm-chart")
	
	# Create LLM prompt for Helm chart generation
	prompt = f"""
You are a Helm expert. Generate a complete Helm chart based on the following information:

**Application Requirements:**
{app_requirements}

**Generated Manifests:**
{manifests_content}

**User Requirements:**
{user_requirements}

**Generate a complete Helm chart with:**
1. Chart.yaml with proper metadata
2. values.yaml with configurable parameters
3. templates/deployment.yaml
4. templates/service.yaml
5. templates/ingress.yaml
6. templates/hpa.yaml
7. templates/configmap.yaml
8. templates/serviceaccount.yaml
9. templates/NOTES.txt with deployment instructions

**Requirements:**
- Make all values configurable through values.yaml
- Use Helm templating best practices
- Include proper conditionals and loops
- Add validation and error handling
- Include comprehensive values.yaml with comments
- Make it production-ready and secure

Generate each file as a separate code block with clear headers.
"""
	
	try:
		response = model.invoke(prompt)
		helm_content = response.content.strip()
		
		# Save Helm chart structure
		chart_dir = os.path.join(output_dir, "my-app")
		templates_dir = os.path.join(chart_dir, "templates")
		os.makedirs(templates_dir, exist_ok=True)
		
		# Parse and save Helm chart files
		sections = helm_content.split('```')
		chart_files = []
		
		for i in range(1, len(sections), 2):
			if i < len(sections):
				header = sections[i-1].strip()
				content = sections[i].strip()
				
				if 'Chart.yaml' in header:
					filepath = os.path.join(chart_dir, "Chart.yaml")
				elif 'values.yaml' in header:
					filepath = os.path.join(chart_dir, "values.yaml")
				elif 'templates/' in header:
					filename = header.split('/')[-1].strip()
					filepath = os.path.join(templates_dir, filename)
				else:
					continue
				
				with open(filepath, 'w') as f:
					f.write(content)
				
				chart_files.append(filepath)
		
		state["helm_chart_content"] = helm_content
		
		response_msg = f"""I've generated a complete Helm chart for your application:

{helm_content}

**Generated files:**
{chr(10).join(f"- {f}" for f in chart_files)}

**Key features implemented:**
- Complete Helm chart structure
- Configurable values.yaml
- Production-ready templates
- Proper Helm templating
- Security best practices
- Auto-scaling configuration
- Comprehensive deployment notes"""
		
		return {"messages": [AIMessage(content=response_msg)]}
		
	except Exception as e:
		error_msg = f"Error generating Helm chart: {str(e)}"
		return {"messages": [AIMessage(content=error_msg)]}

def review_and_optimize_node(state: K8sAgent) -> K8sAgent:
	"""Review and provide optimization recommendations."""
	app_requirements = state.get("app_requirements", "{}")
	manifests_content = state.get("manifests_content", "")
	helm_chart_content = state.get("helm_chart_content", "")
	
	# Create LLM prompt for review and optimization
	prompt = f"""
You are a Kubernetes expert reviewer. Review the following Kubernetes configurations and provide optimization recommendations:

**Application Requirements:**
{app_requirements}

**Generated Manifests:**
{manifests_content}

**Generated Helm Chart:**
{helm_chart_content}

**Review Requirements:**
1. Check for security vulnerabilities and best practices
2. Identify performance optimization opportunities
3. Suggest resource optimization improvements
4. Recommend monitoring and observability setup
5. Provide deployment and scaling strategies
6. Suggest CI/CD integration approaches
7. Recommend backup and disaster recovery strategies
8. Provide troubleshooting and debugging guidance

Provide a comprehensive review with specific recommendations and improvements.
"""
	
	try:
		response = model.invoke(prompt)
		review_content = response.content.strip()
		
		response_msg = f"""## Kubernetes Configuration Review & Optimization

{review_content}

## Next Steps:
1. Review the generated manifests and Helm chart
2. Test with `kubectl apply -f k8s/` or `helm install my-app ./helm-chart/my-app`
3. Implement the suggested optimizations
4. Set up monitoring and logging as recommended
5. Configure CI/CD pipeline for automated deployments
6. Implement backup and disaster recovery strategies

Your Kubernetes setup is now ready for production deployment!"""
		
		return {"messages": [AIMessage(content=response_msg)]}
		
	except Exception as e:
		error_msg = f"Error during review: {str(e)}"
		return {"messages": [AIMessage(content=error_msg)]}

def should_continue(state: K8sAgent) -> str:
	"""Determine the next step in the workflow."""
	
	# Check if we have app requirements
	if not state.get("app_requirements"):
		return "analyze"
	
	# Check if we have manifests content
	if not state.get("manifests_content"):
		return "manifests"
	
	# Check if we have helm chart content
	if not state.get("helm_chart_content"):
		return "helm"
	
	# All done, proceed to review
	return "review"

# Graph
graph = StateGraph(K8sAgent, input_schema=K8sAgent, output_schema=K8sAgent)

# Add nodes
graph.add_node("analyze", analyze_requirements_node)
graph.add_node("manifests", generate_manifests_node)
graph.add_node("helm", generate_helm_chart_node)
graph.add_node("review", review_and_optimize_node)

# Add edges
graph.add_edge(START, "analyze")
graph.add_conditional_edges("analyze", should_continue, {
	"manifests": "manifests",
	"helm": "helm",
	"review": "review"
})
graph.add_conditional_edges("manifests", should_continue, {
	"helm": "helm",
	"review": "review"
})
graph.add_conditional_edges("helm", should_continue, {
	"review": "review"
})
graph.add_edge("review", END)

agent = graph.compile(name="k8s_agent")
