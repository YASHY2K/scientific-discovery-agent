# Bedrock AgentCore MCP Gateway Setup

> **Last Updated:** January 21, 2025  
> **Implementation Status:** Production deployment with 5 Lambda tools registered  
> **Document Version:** 2.0

> **Related Documentation:**
>
> - [System Architecture Overview](../../docs/architecture.md) - Complete system design and component interactions
> - [Comprehensive Implementation Guide](../../docs/comprehensive.md) - Detailed walkthrough of all system components
> - [Agent Architecture](../agent/README.md) - Multi-agent system design and workflow details
> - [Root README](../../README.md) - Project overview and quick start guide

This guide explains how to use the `bedrock_agentcore_starter_toolkit` to create a secure MCP Gateway, configure Cognito authentication, and connect your AWS Lambda tools for agent use.

## Overview

The **AWS Bedrock AgentCore Gateway** provides a secure, authenticated endpoint for agents to access Lambda tools using the Model Context Protocol (MCP). In this system:

- **Agents** (Orchestrator, Planner, Searcher, Analyzer, Critique, Reporter) run in **AWS Bedrock AgentCore Runtime**
- **Tools** (search_arxiv, search_semantic_scholar, acquire_paper, extract_content, preprocess_text) run as **AWS Lambda functions**
- **Gateway** bridges agents and tools with OAuth authentication and IAM permission enforcement

## Features

- Automated creation of a secure AgentCore Gateway with Cognito OAuth authorizer
- MCP protocol support for standardized tool discovery and invocation
- Secure Lambda tool registration with IAM permission enforcement
- Easy extension: add your own Lambda tools and securely connect them to the Gateway

---

## Getting Started

### 1. Prerequisites

- Python 3.12+
- AWS CLI configured (with access to create Lambda, Cognito, and IAM resources)
- `bedrock-agentcore-starter-toolkit` installed:
  ```bash
  pip install bedrock-agentcore-starter-toolkit
  ```

### 2. Create Gateway and Cognito Authorizer

```python
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient
import logging

# Initialize GatewayClient for your AWS region
client = GatewayClient(region_name="us-east-1")
client.logger.setLevel(logging.DEBUG)

# Create Cognito authorizer (creates Cognito User Pool)
cognito_response = client.create_oauth_authorizer_with_cognito("LambdaAuthGW")

# Create the MCP Gateway, secured by the Cognito authorizer
gateway = client.create_mcp_gateway(
    authorizer_config=cognito_response["authorizer_config"]
)

print(f"Gateway created: {gateway['gateway_id']}")
print(f"MCP Endpoint: {gateway['mcp_endpoint']}")
```

### 3. Register Lambda Tools as Gateway Targets

After creating the gateway, register each Lambda tool so agents can access them via MCP protocol.

#### Example: Registering Research System Tools

```python
# Register search_arxiv Lambda
arxiv_target = client.create_mcp_gateway_target(
    gateway=gateway,
    target_type="lambda",
    lambda_arn="arn:aws:lambda:us-east-1:123456789012:function:search_arxiv"
)

# Register search_semantic_scholar Lambda
semantic_target = client.create_mcp_gateway_target(
    gateway=gateway,
    target_type="lambda",
    lambda_arn="arn:aws:lambda:us-east-1:123456789012:function:search_semantic_scholar"
)

# Register acquire_paper Lambda
acquire_target = client.create_mcp_gateway_target(
    gateway=gateway,
    target_type="lambda",
    lambda_arn="arn:aws:lambda:us-east-1:123456789012:function:acquire_paper"
)

# Register extract_content Lambda
extract_target = client.create_mcp_gateway_target(
    gateway=gateway,
    target_type="lambda",
    lambda_arn="arn:aws:lambda:us-east-1:123456789012:function:extract_content"
)

# Register preprocess_text Lambda
preprocess_target = client.create_mcp_gateway_target(
    gateway=gateway,
    target_type="lambda",
    lambda_arn="arn:aws:lambda:us-east-1:123456789012:function:preprocess_text"
)

print(f"Registered {len([arxiv_target, semantic_target, acquire_target, extract_target, preprocess_target])} Lambda tools")
```

### 4. Grant Lambda Invoke Permissions

For every Lambda target, you must grant the Gateway's IAM role permission to invoke it.

#### Using AWS CLI

```bash
# Grant permission for search_arxiv
aws lambda add-permission \
  --function-name search_arxiv \
  --statement-id AllowBedrockInvoke \
  --action lambda:InvokeFunction \
  --principal bedrock.amazonaws.com

# Grant permission for search_semantic_scholar
aws lambda add-permission \
  --function-name search_semantic_scholar \
  --statement-id AllowBedrockInvoke \
  --action lambda:InvokeFunction \
  --principal bedrock.amazonaws.com

# Grant permission for acquire_paper
aws lambda add-permission \
  --function-name acquire_paper \
  --statement-id AllowBedrockInvoke \
  --action lambda:InvokeFunction \
  --principal bedrock.amazonaws.com

# Grant permission for extract_content
aws lambda add-permission \
  --function-name extract_content \
  --statement-id AllowBedrockInvoke \
  --action lambda:InvokeFunction \
  --principal bedrock.amazonaws.com

# Grant permission for preprocess_text
aws lambda add-permission \
  --function-name preprocess_text \
  --statement-id AllowBedrockInvoke \
  --action lambda:InvokeFunction \
  --principal bedrock.amazonaws.com
```

#### Using IAM Policy (Alternative)

Attach this policy to your Lambda function's resource policy:

```json
{
  "Effect": "Allow",
  "Principal": {
    "Service": "bedrock.amazonaws.com"
  },
  "Action": "lambda:InvokeFunction",
  "Resource": "arn:aws:lambda:us-east-1:123456789012:function:search_arxiv"
}
```

### 5. Verify Gateway Configuration

After setup, verify your gateway is properly configured:

```python
# List all registered targets
targets = client.list_mcp_gateway_targets(gateway=gateway)
print(f"Registered tools: {len(targets)}")

for target in targets:
    print(f"- {target['name']}: {target['lambda_arn']}")
```

---

## Tool Registration Details

### Research System Lambda Tools

The multi-agent research system uses five Lambda tools, each with a specific purpose:

| Tool Name                 | Purpose                               | Used By Agent |
| ------------------------- | ------------------------------------- | ------------- |
| `search_arxiv`            | Query arXiv API for academic papers   | Searcher      |
| `search_semantic_scholar` | Query Semantic Scholar API for papers | Searcher      |
| `acquire_paper`           | Download and retrieve paper content   | Searcher      |
| `extract_content`         | Extract text from PDFs, cache in S3   | Analyzer      |
| `preprocess_text`         | Clean and preprocess extracted text   | Analyzer      |

### Tool Invocation Flow

1. **Agent** (running in AgentCore Runtime) decides to use a tool
2. **Agent** calls tool through the **AgentCore Gateway** MCP endpoint
3. **Gateway** authenticates request using Cognito OAuth token
4. **Gateway** verifies IAM permissions for Lambda invocation
5. **Gateway** invokes the **Lambda function**
6. **Lambda** executes deterministic task and returns result
7. **Gateway** returns result to **Agent**
8. **Agent** continues reasoning with tool output

---

## Troubleshooting

### Common Issues and Solutions

#### Issue: "Access Denied" when agent tries to invoke tool

**Symptoms:**

- Agent receives 403 Forbidden error
- Gateway logs show permission denied

**Solutions:**

1. Verify Lambda invoke permission is granted:
   ```bash
   aws lambda get-policy --function-name search_arxiv
   ```
2. Check that `bedrock.amazonaws.com` is in the Principal
3. Re-add permission if missing:
   ```bash
   aws lambda add-permission \
     --function-name search_arxiv \
     --statement-id AllowBedrockInvoke \
     --action lambda:InvokeFunction \
     --principal bedrock.amazonaws.com
   ```

#### Issue: Gateway not found or connection timeout

**Symptoms:**

- Agent cannot connect to gateway endpoint
- Timeout errors in agent logs

**Solutions:**

1. Verify gateway exists:
   ```python
   gateways = client.list_mcp_gateways()
   print(gateways)
   ```
2. Check gateway endpoint URL is correct in agent configuration
3. Verify network connectivity and security groups
4. Ensure Cognito authorizer is properly configured

#### Issue: Tool not appearing in MCP endpoint

**Symptoms:**

- Agent cannot discover tool
- Tool not listed in gateway targets

**Solutions:**

1. Verify tool registration:
   ```python
   targets = client.list_mcp_gateway_targets(gateway=gateway)
   for target in targets:
       print(f"{target['name']}: {target['status']}")
   ```
2. Re-register the tool if missing:
   ```python
   client.create_mcp_gateway_target(
       gateway=gateway,
       target_type="lambda",
       lambda_arn="arn:aws:lambda:us-east-1:123456789012:function:search_arxiv"
   )
   ```
3. Check Lambda function exists and is in the same region

#### Issue: Cognito authentication failures

**Symptoms:**

- 401 Unauthorized errors
- "Invalid token" messages

**Solutions:**

1. Verify Cognito User Pool exists:
   ```bash
   aws cognito-idp list-user-pools --max-results 10
   ```
2. Check OAuth configuration in gateway:
   ```python
   gateway_details = client.get_mcp_gateway(gateway_id=gateway['gateway_id'])
   print(gateway_details['authorizer_config'])
   ```
3. Regenerate OAuth tokens if expired
4. Verify agent is using correct Cognito credentials

#### Issue: Lambda function timeout or errors

**Symptoms:**

- Tool invocation succeeds but returns error
- Lambda execution logs show timeout or exception

**Solutions:**

1. Check Lambda function logs in CloudWatch:
   ```bash
   aws logs tail /aws/lambda/search_arxiv --follow
   ```
2. Verify Lambda has sufficient timeout (recommend 30s minimum)
3. Check Lambda has required IAM permissions (S3, Bedrock, etc.)
4. Test Lambda function directly:
   ```bash
   aws lambda invoke \
     --function-name search_arxiv \
     --payload '{"query": "test"}' \
     response.json
   ```

#### Issue: High latency or slow tool responses

**Symptoms:**

- Agent workflow takes longer than expected
- Gateway metrics show high response times

**Solutions:**

1. Check Lambda cold start times - consider provisioned concurrency
2. Verify S3 caching is working for `extract_content` and `preprocess_text`
3. Monitor Lambda memory allocation - increase if needed
4. Check network latency between AgentCore Runtime and Gateway
5. Review Lambda function code for optimization opportunities

### Debugging Tips

1. **Enable Debug Logging:**

   ```python
   client.logger.setLevel(logging.DEBUG)
   ```

2. **Check Gateway Status:**

   ```python
   gateway_status = client.get_mcp_gateway(gateway_id=gateway['gateway_id'])
   print(f"Status: {gateway_status['status']}")
   print(f"Endpoint: {gateway_status['mcp_endpoint']}")
   ```

3. **Test Tool Registration:**

   ```python
   # List all targets and verify each one
   targets = client.list_mcp_gateway_targets(gateway=gateway)
   expected_tools = ['search_arxiv', 'search_semantic_scholar', 'acquire_paper',
                     'extract_content', 'preprocess_text']

   registered_tools = [t['name'] for t in targets]
   missing_tools = set(expected_tools) - set(registered_tools)

   if missing_tools:
       print(f"Missing tools: {missing_tools}")
   else:
       print("All tools registered successfully")
   ```

4. **Monitor CloudWatch Logs:**
   - Gateway logs: `/aws/bedrock/agentcore/gateway/<gateway-id>`
   - Lambda logs: `/aws/lambda/<function-name>`
   - Agent logs: `/aws/bedrock/agentcore/runtime/<agent-id>`

---

## References

- [Amazon Bedrock AgentCore Gateway Documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/docs/getting-started/intro)
- [AWS Strands Agents SDK Documentation](https://github.com/awslabs/aws-strands-agents-sdk)
- [System Architecture Overview](../../docs/architecture.md)

---

## Security Best Practices

1. **Least Privilege IAM Policies:**

   - Grant only necessary permissions to Lambda functions
   - Use specific resource ARNs instead of wildcards
   - Regularly audit IAM policies

2. **Cognito Configuration:**

   - Enable MFA for Cognito User Pool
   - Set appropriate token expiration times
   - Use secure password policies

3. **Network Security:**

   - Deploy Lambda functions in VPC if accessing private resources
   - Use security groups to restrict traffic
   - Enable VPC endpoints for AWS services

4. **Monitoring and Auditing:**

   - Enable CloudTrail for API call logging
   - Set up CloudWatch alarms for errors and latency
   - Monitor Lambda invocation metrics

5. **Secrets Management:**
   - Store API keys in AWS Secrets Manager
   - Rotate credentials regularly
   - Never hardcode credentials in Lambda code

---

**Note:** This setup is designed for the multi-agent research system. After configuration, your Gateway provides a single, secure MCP endpoint where agents can access all registered Lambda tools with authentication and permission checks enforced by AgentCore and Cognito.

---

## Implementation Status

### ✅ Implemented Gateway Features

- **MCP Gateway**: Secure endpoint for tool discovery and invocation
- **Cognito OAuth Authorizer**: Client credentials flow with automatic token refresh
- **Lambda Tool Registration**: 5 tools registered (search_arxiv, search_semantic_scholar, acquire_paper, extract_content, preprocess_text)
- **IAM Permission Enforcement**: Least privilege access for each Lambda tool
- **Automatic Token Refresh**: MCP client handles 401 errors and token renewal
- **CloudWatch Logging**: Gateway access logs and Lambda invocation tracking
- **SSM Parameter Storage**: Secure configuration management for gateway URL and credentials

### 🚧 Future Gateway Enhancements

- **Rate Limiting**: Per-client throttling to prevent abuse
- **Tool Versioning**: Support for multiple versions of the same tool
- **Custom Authorizers**: Support for additional authentication methods (API keys, IAM)
- **Tool Metrics Dashboard**: Real-time monitoring of tool usage and performance
- **Tool Caching**: Gateway-level caching for idempotent tool responses
- **Multi-Region Gateway**: Geographic distribution for improved latency
- **Tool Discovery API**: Dynamic tool registration without redeployment
- **Request/Response Transformation**: Gateway-level data mapping and validation

### ❌ Not Implemented

The following features were considered but **not implemented**:

- **API Gateway Integration**: Direct MCP endpoint used instead
- **WebSocket Support**: Synchronous HTTP-based MCP protocol sufficient
- **Custom Domain Names**: Using default AWS endpoint
- **VPC Integration**: Public endpoint with OAuth sufficient for current security requirements
- **Request Validation**: Handled by Lambda functions instead of gateway
- **Response Caching**: S3-based caching in tools more effective

These features may be added based on production requirements and scale needs.
