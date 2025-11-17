"""
Azure MCP Server with comprehensive Azure tools
Based on latest MCP documentation and Azure SDK patterns
"""

import os
import asyncio
from typing import Optional, Dict, List, Any
from mcp.server.fastmcp import FastMCP
from azure.identity import DefaultAzureCredential, ClientSecretCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.containerservice import ContainerServiceClient
from azure.mgmt.containerregistry import ContainerRegistryManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.sql import SqlManagementClient
from azure.mgmt.redis import RedisManagementClient
from azure.mgmt.keyvault import KeyVaultManagementClient
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP("azure-comprehensive-server")

# Azure configuration
SUBSCRIPTION_ID = os.getenv("AZURE_SUBSCRIPTION_ID", "")
TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")

# Initialize Azure credential
def get_credential():
    """Get Azure credential based on available authentication methods."""
    try:
        if CLIENT_ID and CLIENT_SECRET and TENANT_ID:
            return ClientSecretCredential(
                tenant_id=TENANT_ID,
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET
            )
        else:
            return DefaultAzureCredential()
    except Exception as e:
        logger.error(f"Failed to initialize Azure credential: {e}")
        return None

credential = get_credential()

# Initialize Azure clients
def get_resource_client():
    return ResourceManagementClient(credential, SUBSCRIPTION_ID)

def get_compute_client():
    return ComputeManagementClient(credential, SUBSCRIPTION_ID)

def get_storage_client():
    return StorageManagementClient(credential, SUBSCRIPTION_ID)

def get_aks_client():
    return ContainerServiceClient(credential, SUBSCRIPTION_ID)

def get_acr_client():
    return ContainerRegistryManagementClient(credential, SUBSCRIPTION_ID)

def get_sql_client():
    return SqlManagementClient(credential, SUBSCRIPTION_ID)

def get_redis_client():
    return RedisManagementClient(credential, SUBSCRIPTION_ID)

def get_keyvault_client():
    return KeyVaultManagementClient(credential, SUBSCRIPTION_ID)

# Resource Group Tools
@mcp.tool()
def create_resource_group(name: str, location: str = "eastus") -> dict:
    """Create an Azure Resource Group"""
    try:
        resource_client = get_resource_client()
        rg_params = {"location": location}
        rg = resource_client.resource_groups.create_or_update(name, rg_params)
        return {
            "status": "success",
            "name": rg.name,
            "location": rg.location,
            "id": rg.id
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
def list_resource_groups() -> dict:
    """List all Resource Groups in the subscription"""
    try:
        resource_client = get_resource_client()
        rgs = list(resource_client.resource_groups.list())
        return {
            "status": "success",
            "resource_groups": [
                {
                    "name": rg.name,
                    "location": rg.location,
                    "id": rg.id,
                    "provisioning_state": rg.provisioning_state
                }
                for rg in rgs
            ]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
def delete_resource_group(name: str) -> dict:
    """Delete an Azure Resource Group"""
    try:
        resource_client = get_resource_client()
        operation = resource_client.resource_groups.begin_delete(name)
        return {
            "status": "success",
            "message": f"Resource group {name} deletion initiated"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Virtual Machine Tools
@mcp.tool()
def list_virtual_machines(resource_group_name: Optional[str] = None) -> dict:
    """List Virtual Machines in subscription or resource group"""
    try:
        compute_client = get_compute_client()
        if resource_group_name:
            vms = list(compute_client.virtual_machines.list(resource_group_name))
        else:
            vms = list(compute_client.virtual_machines.list_all())
        
        return {
            "status": "success",
            "virtual_machines": [
                {
                    "name": vm.name,
                    "location": vm.location,
                    "vm_size": vm.hardware_profile.vm_size if vm.hardware_profile else None,
                    "provisioning_state": vm.provisioning_state,
                    "id": vm.id
                }
                for vm in vms
            ]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Storage Account Tools
@mcp.tool()
def list_storage_accounts(resource_group_name: Optional[str] = None) -> dict:
    """List Storage Accounts in subscription or resource group"""
    try:
        storage_client = get_storage_client()
        if resource_group_name:
            accounts = list(storage_client.storage_accounts.list_by_resource_group(resource_group_name))
        else:
            accounts = list(storage_client.storage_accounts.list())
        
        return {
            "status": "success",
            "storage_accounts": [
                {
                    "name": account.name,
                    "location": account.location,
                    "sku": account.sku.name if account.sku else None,
                    "kind": account.kind,
                    "provisioning_state": account.provisioning_state,
                    "id": account.id
                }
                for account in accounts
            ]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# AKS Tools
@mcp.tool()
def list_aks_clusters(resource_group_name: Optional[str] = None) -> dict:
    """List AKS clusters in subscription or resource group"""
    try:
        aks_client = get_aks_client()
        if resource_group_name:
            clusters = list(aks_client.managed_clusters.list_by_resource_group(resource_group_name))
        else:
            clusters = list(aks_client.managed_clusters.list())
        
        return {
            "status": "success",
            "aks_clusters": [
                {
                    "name": cluster.name,
                    "location": cluster.location,
                    "kubernetes_version": cluster.kubernetes_version,
                    "provisioning_state": cluster.provisioning_state,
                    "node_count": cluster.agent_pool_profiles[0].count if cluster.agent_pool_profiles else 0,
                    "id": cluster.id
                }
                for cluster in clusters
            ]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Health check endpoint
@mcp.tool()
def health_check() -> dict:
    """Check the health of the Azure MCP server"""
    try:
        # Test credential by listing resource groups (lightweight operation)
        resource_client = get_resource_client()
        rgs = list(resource_client.resource_groups.list())
        
        return {
            "status": "healthy",
            "subscription_id": SUBSCRIPTION_ID,
            "credential_type": type(credential).__name__,
            "resource_groups_count": len(rgs),
            "tools_available": [
                "create_resource_group", "list_resource_groups", "delete_resource_group",
                "list_virtual_machines", "list_storage_accounts", 
                "list_aks_clusters", "health_check"
            ]
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "subscription_id": SUBSCRIPTION_ID
        }

if __name__ == "__main__":
    if not credential:
        logger.error("Failed to initialize Azure credentials. Please ensure authentication is configured.")
        exit(1)
    
    if not SUBSCRIPTION_ID:
        logger.error("AZURE_SUBSCRIPTION_ID environment variable is required.")
        exit(1)
    
    logger.info(f"Starting Azure MCP Server for subscription: {SUBSCRIPTION_ID}")
    logger.info(f"Using credential type: {type(credential).__name__}")
    
    mcp.run()