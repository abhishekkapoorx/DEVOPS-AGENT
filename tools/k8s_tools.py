import os
import json
import yaml
from typing import Dict, Any, List, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class ManifestInput(BaseModel):
    """Input for Kubernetes manifest generation."""
    app_name: str = Field(description="Name of the application")
    app_type: str = Field(description="Type of application (web, api, database, etc.)")
    image: str = Field(description="Docker image to deploy")
    port: int = Field(default=8080, description="Port the application listens on")
    replicas: int = Field(default=3, description="Number of replicas")
    environment: str = Field(default="production", description="Environment (development, staging, production)")
    resources: Optional[Dict[str, Any]] = Field(default=None, description="Resource requirements and limits")
    env_vars: Optional[Dict[str, str]] = Field(default=None, description="Environment variables")
    output_dir: str = Field(description="Directory to save the generated manifests")


def _generate_deployment(app_name: str, app_type: str, image: str, port: int, 
                         replicas: int, environment: str, resources: Optional[Dict[str, Any]], 
                         env_vars: Optional[Dict[str, str]]) -> Dict[str, Any]:
    """Generate Deployment manifest."""
    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": app_name,
            "labels": {
                "app": app_name,
                "environment": environment,
                "type": app_type
            }
        },
        "spec": {
            "replicas": replicas,
            "selector": {
                "matchLabels": {
                    "app": app_name
                }
            },
            "template": {
                "metadata": {
                    "labels": {
                        "app": app_name,
                        "environment": environment
                    }
                },
                "spec": {
                    "containers": [{
                        "name": app_name,
                        "image": image,
                        "ports": [{
                            "containerPort": port,
                            "name": "http"
                        }],
                        "env": _format_env_vars(env_vars),
                        "resources": _format_resources(resources),
                        "livenessProbe": {
                            "httpGet": {
                                "path": "/health",
                                "port": port
                            },
                            "initialDelaySeconds": 30,
                            "periodSeconds": 10
                        },
                        "readinessProbe": {
                            "httpGet": {
                                "path": "/ready",
                                "port": port
                            },
                            "initialDelaySeconds": 5,
                            "periodSeconds": 5
                        }
                    }],
                    "securityContext": {
                        "runAsNonRoot": True,
                        "runAsUser": 1000,
                        "fsGroup": 2000
                    }
                }
            }
        }
    }
    return deployment

def _generate_service(app_name: str, port: int) -> Dict[str, Any]:
    """Generate Service manifest."""
    service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": f"{app_name}-service",
            "labels": {
                "app": app_name
            }
        },
        "spec": {
            "selector": {
                "app": app_name
            },
            "ports": [{
                "port": 80,
                "targetPort": port,
                "protocol": "TCP",
                "name": "http"
            }],
            "type": "ClusterIP"
        }
    }
    return service

def _generate_configmap(app_name: str, env_vars: Optional[Dict[str, str]]) -> Dict[str, Any]:
    """Generate ConfigMap manifest."""
    configmap = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": f"{app_name}-config",
            "labels": {
                "app": app_name
            }
        },
        "data": env_vars or {}
    }
    return configmap

def _generate_ingress(app_name: str, port: int) -> Dict[str, Any]:
    """Generate Ingress manifest."""
    ingress = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {
            "name": f"{app_name}-ingress",
            "labels": {
                "app": app_name
            },
            "annotations": {
                "nginx.ingress.kubernetes.io/rewrite-target": "/",
                "nginx.ingress.kubernetes.io/ssl-redirect": "false"
            }
        },
        "spec": {
            "ingressClassName": "nginx",
            "rules": [{
                "host": f"{app_name}.example.com",
                "http": {
                    "paths": [{
                        "path": "/",
                        "pathType": "Prefix",
                        "backend": {
                            "service": {
                                "name": f"{app_name}-service",
                                "port": {
                                    "number": 80
                                }
                            }
                        }
                    }]
                }
            }]
        }
    }
    return ingress

def _generate_hpa(app_name: str, replicas: int) -> Dict[str, Any]:
    """Generate HorizontalPodAutoscaler manifest."""
    hpa = {
        "apiVersion": "autoscaling/v2",
        "kind": "HorizontalPodAutoscaler",
        "metadata": {
            "name": f"{app_name}-hpa",
            "labels": {
                "app": app_name
            }
        },
        "spec": {
            "scaleTargetRef": {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "name": app_name
            },
            "minReplicas": max(1, replicas // 2),
            "maxReplicas": replicas * 3,
            "metrics": [{
                "type": "Resource",
                "resource": {
                    "name": "cpu",
                    "target": {
                        "type": "Utilization",
                        "averageUtilization": 70
                    }
                }
            }]
        }
    }
    return hpa

def _format_env_vars(env_vars: Optional[Dict[str, str]]) -> List[Dict[str, str]]:
    """Format environment variables for Kubernetes."""
    if not env_vars:
        return []
    return [{"name": k, "value": v} for k, v in env_vars.items()]

def _format_resources(resources: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Format resource requirements and limits."""
    if not resources:
        return {
            "requests": {
                "memory": "128Mi",
                "cpu": "100m"
            },
            "limits": {
                "memory": "512Mi",
                "cpu": "500m"
            }
        }
    return resources

def _save_manifest(manifest: Dict[str, Any], filepath: str) -> None:
    """Save manifest to YAML file."""
    with open(filepath, 'w') as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)


class HelmChartInput(BaseModel):
    """Input for Helm chart generation."""
    app_name: str = Field(description="Name of the application")
    app_type: str = Field(description="Type of application (web, api, database, etc.)")
    image: str = Field(description="Docker image to deploy")
    port: int = Field(default=8080, description="Port the application listens on")
    replicas: int = Field(default=3, description="Number of replicas")
    environment: str = Field(default="production", description="Environment")
    output_dir: str = Field(description="Directory to save the Helm chart")
    values: Optional[Dict[str, Any]] = Field(default=None, description="Custom values for the chart")


def _generate_chart_yaml(chart_dir: str, app_name: str) -> None:
    """Generate Chart.yaml file."""
    chart_yaml = {
        "apiVersion": "v2",
        "name": app_name,
        "description": f"A Helm chart for {app_name}",
        "type": "application",
        "version": "0.1.0",
        "appVersion": "1.0.0"
    }
    
    with open(os.path.join(chart_dir, "Chart.yaml"), 'w') as f:
        yaml.dump(chart_yaml, f, default_flow_style=False)

def _generate_values_yaml(chart_dir: str, app_name: str, app_type: str, 
                          image: str, port: int, replicas: int, environment: str, 
                          custom_values: Optional[Dict[str, Any]]) -> None:
    """Generate values.yaml file."""
    values = {
        "replicaCount": replicas,
        "image": {
            "repository": image.split(':')[0],
            "pullPolicy": "IfNotPresent",
            "tag": image.split(':')[1] if ':' in image else "latest"
        },
        "imagePullSecrets": [],
        "nameOverride": "",
        "fullnameOverride": "",
        "serviceAccount": {
            "create": True,
            "annotations": {},
            "name": ""
        },
        "podAnnotations": {},
        "podSecurityContext": {
            "fsGroup": 2000,
            "runAsNonRoot": True,
            "runAsUser": 1000
        },
        "securityContext": {
            "allowPrivilegeEscalation": False,
            "capabilities": {
                "drop": ["ALL"]
            },
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 1000
        },
        "service": {
            "type": "ClusterIP",
            "port": 80,
            "targetPort": port
        },
        "ingress": {
            "enabled": True,
            "className": "nginx",
            "annotations": {
                "nginx.ingress.kubernetes.io/rewrite-target": "/"
            },
            "hosts": [{
                "host": f"{app_name}.example.com",
                "paths": [{
                    "path": "/",
                    "pathType": "Prefix"
                }]
            }],
            "tls": []
        },
        "resources": {
            "limits": {
                "cpu": "500m",
                "memory": "512Mi"
            },
            "requests": {
                "cpu": "100m",
                "memory": "128Mi"
            }
        },
        "autoscaling": {
            "enabled": True,
            "minReplicas": max(1, replicas // 2),
            "maxReplicas": replicas * 3,
            "targetCPUUtilizationPercentage": 70
        },
        "nodeSelector": {},
        "tolerations": [],
        "affinity": {},
        "env": {
            "ENVIRONMENT": environment,
            "APP_NAME": app_name
        }
    }
    
    # Merge custom values if provided
    if custom_values:
        values.update(custom_values)
    
    with open(os.path.join(chart_dir, "values.yaml"), 'w') as f:
        yaml.dump(values, f, default_flow_style=False)

def _generate_deployment_template(templates_dir: str, app_name: str) -> None:
    """Generate deployment template."""
    deployment_template = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "{{ .Chart.Name }}.fullname" . }}
  labels:
    {{- include "{{ .Chart.Name }}.labels" . | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "{{ .Chart.Name }}.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      {{- with .Values.podAnnotations }}
      annotations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      labels:
        {{- include "{{ .Chart.Name }}.selectorLabels" . | nindent 8 }}
    spec:
      {{- with .Values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      serviceAccountName: {{ include "{{ .Chart.Name }}.serviceAccountName" . }}
      securityContext:
        {{- toYaml .Values.podSecurityContext | nindent 8 }}
      containers:
        - name: {{ .Chart.Name }}
          securityContext:
            {{- toYaml .Values.securityContext | nindent 12 }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: {{ .Values.service.targetPort }}
              protocol: TCP
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: http
            initialDelaySeconds: 5
            periodSeconds: 5
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          env:
            {{- range $key, $value := .Values.env }}
            - name: {{ $key }}
              value: {{ $value | quote }}
            {{- end }}
      {{- with .Values.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.affinity }}
      affinity:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.tolerations }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
"""
    
    with open(os.path.join(templates_dir, "deployment.yaml"), 'w') as f:
        f.write(deployment_template)

def _generate_service_template(templates_dir: str, app_name: str) -> None:
    """Generate service template."""
    service_template = """apiVersion: v1
kind: Service
metadata:
  name: {{ include "{{ .Chart.Name }}.fullname" . }}
  labels:
    {{- include "{{ .Chart.Name }}.labels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: http
      protocol: TCP
      name: http
  selector:
    {{- include "{{ .Chart.Name }}.selectorLabels" . | nindent 4 }}
"""
    
    with open(os.path.join(templates_dir, "service.yaml"), 'w') as f:
        f.write(service_template)

def _generate_ingress_template(templates_dir: str, app_name: str) -> None:
    """Generate ingress template."""
    ingress_template = """{{- if .Values.ingress.enabled -}}
{{- $fullName := include "{{ .Chart.Name }}.fullname" . -}}
{{- $svcPort := .Values.service.port -}}
{{- if and .Values.ingress.className (not (hasKey .Values.ingress.annotations "kubernetes.io/ingress.class")) }}
  {{- $_ := set .Values.ingress.annotations "kubernetes.io/ingress.class" .Values.ingress.className}}
{{- end }}
{{- if semverCompare ">=1.19-0" .Capabilities.KubeVersion.GitVersion -}}
apiVersion: networking.k8s.io/v1
{{- else if semverCompare ">=1.14-0" .Capabilities.KubeVersion.GitVersion -}}
apiVersion: networking.k8s.io/v1beta1
{{- else -}}
apiVersion: extensions/v1beta1
{{- end }}
kind: Ingress
metadata:
  name: {{ $fullName }}
  labels:
    {{- include "{{ .Chart.Name }}.labels" . | nindent 4 }}
  {{- with .Values.ingress.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  {{- if and .Values.ingress.className (semverCompare ">=1.18-0" .Capabilities.KubeVersion.GitVersion) }}
  ingressClassName: {{ .Values.ingress.className }}
  {{- end }}
  {{- if .Values.ingress.tls }}
  tls:
    {{- range .Values.ingress.tls }}
    - hosts:
        {{- range .hosts }}
        - {{ . | quote }}
        {{- end }}
      secretName: {{ .secretName }}
    {{- end }}
  {{- end }}
  rules:
    {{- range .Values.ingress.hosts }}
    - host: {{ .host | quote }}
      http:
        paths:
          {{- range .paths }}
          - path: {{ .path }}
            {{- if and .pathType (semverCompare ">=1.18-0" $.Capabilities.KubeVersion.GitVersion) }}
            pathType: {{ .pathType }}
            {{- end }}
            backend:
              {{- if semverCompare ">=1.19-0" $.Capabilities.KubeVersion.GitVersion }}
              service:
                name: {{ $fullName }}
                port:
                  number: {{ $svcPort }}
              {{- else }}
              serviceName: {{ $fullName }}
              servicePort: {{ $svcPort }}
              {{- end }}
          {{- end }}
    {{- end }}
{{- end }}
"""
    
    with open(os.path.join(templates_dir, "ingress.yaml"), 'w') as f:
        f.write(ingress_template)

def _generate_hpa_template(templates_dir: str, app_name: str) -> None:
    """Generate HPA template."""
    hpa_template = """{{- if .Values.autoscaling.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ include "{{ .Chart.Name }}.fullname" . }}
  labels:
    {{- include "{{ .Chart.Name }}.labels" . | nindent 4 }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ include "{{ .Chart.Name }}.fullname" . }}
  minReplicas: {{ .Values.autoscaling.minReplicas }}
  maxReplicas: {{ .Values.autoscaling.maxReplicas }}
  metrics:
    {{- if .Values.autoscaling.targetCPUUtilizationPercentage }}
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ 
 .Values.autoscaling.targetCPUUtilizationPercentage }}
    {{- end }}
    {{- if .Values.autoscaling.targetMemoryUtilizationPercentage }}
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: {{ .Values.autoscaling.targetMemoryUtilizationPercentage }}
    {{- end }}
{{- end }}
"""
    
    with open(os.path.join(templates_dir, "hpa.yaml"), 'w') as f:
        f.write(hpa_template)

def _generate_notes_txt(templates_dir: str, app_name: str) -> None:
    """Generate NOTES.txt template."""
    notes_template = """1. Get the application URL by running these commands:
{{- if .Values.ingress.enabled }}
{{- range $host := .Values.ingress.hosts }}
  {{- range .paths }}
  http{{ if $.Values.ingress.tls }}s{{ end }}://{{ $host.host }}{{ .path }}
  {{- end }}
{{- end }}
{{- else if contains "NodePort" .Values.service.type }}
  export NODE_PORT=$(kubectl get --namespace {{ .Release.Namespace }} -o jsonpath="{.spec.ports[0].nodePort}" services {{ include "{{ .Chart.Name }}.fullname" . }})
  export NODE_IP=$(kubectl get nodes --namespace {{ .Release.Namespace }} -o jsonpath="{.items[0].status.addresses[0].address}")
  echo http://$NODE_IP:$NODE_PORT
{{- else if contains "LoadBalancer" .Values.service.type }}
     NOTE: It may take a few minutes for the LoadBalancer IP to be available.
           You can watch the status of by running 'kubectl get --namespace {{ .Release.Namespace }} svc -w {{ include "{{ .Chart.Name }}.fullname" . }}'
  export SERVICE_IP=$(kubectl get svc --namespace {{ .Release.Namespace }} {{ include "{{ .Chart.Name }}.fullname" . }} --template "{{"{{ range (index .status.loadBalancer.ingress 0) }}{{.}}{{ end }}"}}")
  echo http://$SERVICE_IP:{{ .Values.service.port }}
{{- else if contains "ClusterIP" .Values.service.type }}
  export POD_NAME=$(kubectl get pods --namespace {{ .Release.Namespace }} -l "app.kubernetes.io/name={{ include "{{ .Chart.Name }}.name" . }},app.kubernetes.io/instance={{ .Release.Name }}" -o jsonpath="{.items[0].metadata.name}")
  export CONTAINER_PORT=$(kubectl get pod --namespace {{ .Release.Namespace }} $POD_NAME -o jsonpath="{.spec.containers[0].ports[0].containerPort}")
  echo "Visit http://127.0.0.1:8080 to use your application"
  kubectl --namespace {{ .Release.Namespace }} port-forward $POD_NAME 8080:$CONTAINER_PORT
{{- end }}
"""
    
    with open(os.path.join(templates_dir, "NOTES.txt"), 'w') as f:
        f.write(notes_template)


class ServiceGeneratorInput(BaseModel):
    """Input for Kubernetes service generation."""
    service_name: str = Field(description="Name of the service")
    service_type: str = Field(default="ClusterIP", description="Type of service (ClusterIP, NodePort, LoadBalancer)")
    port: int = Field(description="Port to expose")
    target_port: int = Field(description="Target port on the pods")
    selector: Dict[str, str] = Field(description="Pod selector labels")
    output_path: str = Field(description="Path to save the service manifest")


@tool("generate_k8s_manifests", args_schema=ManifestInput)
def generate_k8s_manifests(app_name: str, app_type: str, image: str, port: int = 8080, 
                           replicas: int = 3, environment: str = "production", 
                           resources: Optional[Dict[str, Any]] = None, 
                           env_vars: Optional[Dict[str, str]] = None, 
                           output_dir: str = "./k8s") -> str:
    """Generate comprehensive Kubernetes manifests including Deployments, Services, ConfigMaps, Ingress, and HPA."""
    try:
        os.makedirs(output_dir, exist_ok=True)
        deployment = _generate_deployment(app_name, app_type, image, port, replicas, environment, resources, env_vars)
        service = _generate_service(app_name, port)
        configmap = _generate_configmap(app_name, env_vars)
        ingress = _generate_ingress(app_name, port)
        hpa = _generate_hpa(app_name, replicas)
        _save_manifest(deployment, os.path.join(output_dir, f"{app_name}-deployment.yaml"))
        _save_manifest(service, os.path.join(output_dir, f"{app_name}-service.yaml"))
        _save_manifest(configmap, os.path.join(output_dir, f"{app_name}-configmap.yaml"))
        _save_manifest(ingress, os.path.join(output_dir, f"{app_name}-ingress.yaml"))
        _save_manifest(hpa, os.path.join(output_dir, f"{app_name}-hpa.yaml"))
        return f"Kubernetes manifests generated successfully in {output_dir}/"
    except Exception as e:
        return f"Error generating Kubernetes manifests: {str(e)}"

@tool("generate_helm_chart", args_schema=HelmChartInput)
def generate_helm_chart(app_name: str, app_type: str, image: str, port: int = 8080, 
                        replicas: int = 3, environment: str = "production", 
                        output_dir: str = "./helm-chart", 
                        values: Optional[Dict[str, Any]] = None) -> str:
    """Generate a complete Helm chart with templates, values, and Chart.yaml."""
    try:
        chart_dir = os.path.join(output_dir, app_name)
        templates_dir = os.path.join(chart_dir, "templates")
        os.makedirs(templates_dir, exist_ok=True)
        _generate_chart_yaml(chart_dir, app_name)
        _generate_values_yaml(chart_dir, app_name, app_type, image, port, replicas, environment, values)
        _generate_deployment_template(templates_dir, app_name)
        _generate_service_template(templates_dir, app_name)
        _generate_ingress_template(templates_dir, app_name)
        _generate_hpa_template(templates_dir, app_name)
        _generate_notes_txt(templates_dir, app_name)
        return f"Helm chart generated successfully in {chart_dir}/"
    except Exception as e:
        return f"Error generating Helm chart: {str(e)}"

@tool("generate_k8s_service", args_schema=ServiceGeneratorInput)
def generate_k8s_service(service_name: str, service_type: str, port: int, target_port: int, 
                         selector: Dict[str, str], output_path: str) -> str:
    """Generate a Kubernetes Service manifest."""
    try:
        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": service_name,
                "labels": {
                    "app": service_name
                }
            },
            "spec": {
                "type": service_type,
                "selector": selector,
                "ports": [{
                    "port": port,
                    "targetPort": target_port,
                    "protocol": "TCP",
                    "name": "http"
                }]
            }
        }
        _save_manifest(service, output_path)
        return f"Kubernetes service manifest generated successfully at {output_path}"
    except Exception as e:
        return f"Error generating Kubernetes service: {str(e)}"
