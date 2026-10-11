# AWS Agent handoff tool
from langgraph_supervisor.handoff import create_handoff_tool

aws_agent_handoff = create_handoff_tool(
    agent_name="aws_agent",
    name="aws_agent",
    description="""
    Handoff to AWS Agent for Amazon Web Services infrastructure tasks.

    Scope:
    - EC2 instances, ECS, EKS, Lambda functions
    - RDS databases, DynamoDB, ElastiCache
    - S3 buckets, CloudFront, Route 53
    - VPC, Security Groups, IAM roles and policies
    - CloudWatch monitoring, CloudTrail logging
    - Auto Scaling Groups, Load Balancers
    - SQS, SNS, EventBridge messaging
    - CodeDeploy, CodePipeline CI/CD

    Behavior:
    - Operates autonomously using AWS CLI/SDK
    - Follows THINK-PLAN-ACT-REFLECT operational loop
    - Provides detailed infrastructure plans and cost analysis
    - Implements security best practices and compliance
    - No manual user intervention required
    """
)

# Azure Agent handoff tool
azure_agent_handoff = create_handoff_tool(
    agent_name="azure_agent",
    name="azure_agent",
    description="""
    Handoff to Azure Agent for Microsoft Azure infrastructure tasks.

    Scope:
    - Virtual Machines, Container Instances, AKS
    - Azure SQL Database, Cosmos DB, Redis Cache
    - Blob Storage, CDN, Traffic Manager
    - Virtual Networks, Network Security Groups, RBAC
    - Application Insights, Log Analytics
    - Virtual Machine Scale Sets, Load Balancers
    - Service Bus, Event Grid, Logic Apps
    - Azure DevOps, GitHub Actions integration

    Behavior:
    - Operates autonomously using Azure CLI/PowerShell
    - Follows THINK-PLAN-ACT-REFLECT operational loop
    - Provides detailed infrastructure plans and cost analysis
    - Implements security best practices and compliance
    - No manual user intervention required
    """
)

# GCP Agent handoff tool
gcp_agent_handoff = create_handoff_tool(
    agent_name="gcp_agent",
    name="gcp_agent",
    description="""
    Handoff to GCP Agent for Google Cloud Platform infrastructure tasks.

    Scope:
    - Compute Engine, Cloud Run, GKE
    - Cloud SQL, Firestore, Memorystore
    - Cloud Storage, Cloud CDN, Cloud DNS
    - VPC, Firewall Rules, IAM policies
    - Cloud Monitoring, Cloud Logging
    - Managed Instance Groups, Load Balancers
    - Pub/Sub, Cloud Functions, Workflows
    - Cloud Build, Cloud Deploy CI/CD

    Behavior:
    - Operates autonomously using gcloud CLI/SDK
    - Follows THINK-PLAN-ACT-REFLECT operational loop
    - Provides detailed infrastructure plans and cost analysis
    - Implements security best practices and compliance
    - No manual user intervention required
    """
)

all_cloud_agent_handoffs = [aws_agent_handoff, azure_agent_handoff, gcp_agent_handoff]