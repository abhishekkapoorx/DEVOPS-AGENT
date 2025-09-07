# AWS Agent with MCP Tools

This AWS Agent uses LangGraph's `create_react_agent` and integrates AWS tools through the Model Context Protocol (MCP).

## Features

The AWS Agent provides access to the following AWS services through MCP tools:

- **EC2**: List instances, describe VPCs, security groups
- **S3**: List buckets
- **IAM**: List users, get account information
- **Lambda**: List functions
- **RDS**: List database instances
- **CloudFormation**: List stacks
- **General**: Get AWS regions

## Prerequisites

1. **AWS Credentials**: Configure your AWS credentials using one of these methods:
   ```bash
   # Option 1: AWS CLI
   aws configure
   
   # Option 2: Environment variables
   export AWS_ACCESS_KEY_ID=your_access_key
   export AWS_SECRET_ACCESS_KEY=your_secret_key
   export AWS_DEFAULT_REGION=us-east-1
   
   # Option 3: IAM roles (if running on EC2)
   ```

2. **Dependencies**: Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

## Files

- `AWSAgent.py`: Main agent implementation using `create_react_agent`
- `aws_mcp_server.py`: MCP server providing AWS tools
- `aws_mcp_client.py`: Async client wrapper for MCP operations
- `example_aws_usage.py`: Example usage script

## Usage

### Basic Usage

```python
from agents.CloudAgent.AWSAgent import agent

# The agent is ready to use
response = await agent.ainvoke({
    "messages": [{"role": "user", "content": "List my EC2 instances"}]
})
```

### With MCP Tools (Async)

```python
import asyncio
from agents.CloudAgent.aws_mcp_client import get_aws_agent

async def main():
    # Get agent with MCP tools
    agent = await get_aws_agent()
    
    # Use the agent
    response = await agent.ainvoke({
        "messages": [{"role": "user", "content": "Show me my S3 buckets"}]
    })
    
    print(response)

asyncio.run(main())
```

### Example Script

Run the example script to test all AWS tools:

```bash
cd agents/CloudAgent
python example_aws_usage.py
```

## Available Tools

The AWS MCP server provides these tools:

1. `list_ec2_instances()` - List all EC2 instances
2. `list_s3_buckets()` - List all S3 buckets
3. `list_iam_users()` - List all IAM users
4. `list_lambda_functions()` - List all Lambda functions
5. `list_rds_instances()` - List all RDS instances
6. `list_cloudformation_stacks()` - List all CloudFormation stacks
7. `get_aws_account_info()` - Get AWS account information
8. `describe_vpcs()` - Describe VPCs in the current region
9. `describe_security_groups()` - Describe security groups
10. `get_aws_regions()` - Get list of available AWS regions

## Error Handling

The agent includes comprehensive error handling:

- **Credential Issues**: Provides clear guidance on AWS credential configuration
- **Permission Issues**: Explains IAM permission requirements
- **Network Issues**: Suggests troubleshooting steps
- **Service Unavailable**: Graceful fallback with helpful messages

## Integration with Supervisor

The AWS Agent integrates with the main supervisor system:

```python
from agents.CloudAgent import aws_agent

# The agent is automatically available to the Cloud Agent supervisor
```

## Security Notes

- The agent only provides read-only operations by default
- Ensure AWS credentials have minimal required permissions
- Consider using IAM roles instead of access keys when possible
- Review and audit all AWS API calls made by the agent

## Troubleshooting

### Common Issues

1. **"AWS client not initialized"**
   - Check AWS credentials configuration
   - Verify boto3 installation
   - Ensure AWS region is set

2. **"Permission denied"**
   - Check IAM permissions for the AWS user/role
   - Ensure the user has read access to required services

3. **"MCP tools not available"**
   - Verify MCP server is running
   - Check Python path and dependencies
   - Review MCP server logs

### Debug Mode

Enable debug logging by setting the log level:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Contributing

To add new AWS tools:

1. Add the tool function to `aws_mcp_server.py`
2. Update the agent prompt in `aws_mcp_client.py`
3. Test the new tool with the example script
4. Update this README with the new tool documentation

