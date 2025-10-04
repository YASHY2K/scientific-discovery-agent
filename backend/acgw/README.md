Below is a README documenting your process based on the given code and the described additional steps, suitable for sharing internally or in a repository.

---

# Bedrock AgentCore MCP Gateway Quickstart

This guide explains how to use the `bedrock_agentcore_starter_toolkit` to quickly create a secure MCP Gateway, configure Cognito authentication, and connect your AWS Lambda tools for agent use.

---

## Features

- Automated creation of a secure AgentCore Gateway with Cognito OAuth authorizer.
- Example Lambda function deployed and made available as a tool.
- Easy extension: add your own Lambda tools and securely connect them to the Gateway.

---

## Getting Started

### 1. Prerequisites

- Python 3.12+
- AWS CLI configured (with access to create Lambda, Cognito, and IAM resources)
- `bedrock-agentcore-starter-toolkit` installed:
  ```bash
  pip install bedrock-agentcore-starter-toolkit
  ```

---

### 2. Example Code

```python
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient
import logging

# Setup GatewayClient for the desired AWS region
client = GatewayClient(region_name="us-east-1")
client.logger.setLevel(logging.DEBUG)

# (1) Create Cognito authorizer (creates Cognito User Pool)
cognito_response = client.create_oauth_authorizer_with_cognito("LambdaAuthGW")

# (2) Create the MCP Gateway, secured by the Cognito authorizer
gateway = client.create_mcp_gateway(
    authorizer_config=cognito_response["authorizer_config"]
)

# (3) Optionally, create/add a new Lambda tool as a gateway target
lambda_target = client.create_mcp_gateway_target(gateway=gateway, target_type="lambda")
```

---

### 3. Additional Steps and Security

1. **Resource Creation**

   - The toolkit will automatically create:
     - An AgentCore Gateway
     - A new Cognito User Pool (for OAuth/JWT authentication)
     - A test Lambda function

2. **Grant Lambda Invoke Permissions**

   - For every Lambda target (including custom ones), attach an IAM policy **allowing the Gateway’s IAM Role to invoke your Lambda**.
   - Example policy action on your Lambda function:
     ```json
     {
       "Action": "lambda:InvokeFunction",
       "Effect": "Allow",
       "Principal": {
         "Service": "bedrock.amazonaws.com"
       },
       "Resource": "<YourLambdaArn>"
     }
     ```
   - This can be done using the AWS Console or AWS CLI.

3. **Add Additional Lambda Targets**
   - Use `client.create_mcp_gateway_target()` to add more Lambdas as tools available at your gateway’s MCP endpoint.

---

## References

- [Amazon Bedrock AgentCore Gateway Documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/docs/getting-started/intro)

---

**Note:** The above script is intended for development and demonstration. In production, secure credentials, review IAM roles, and apply least privilege best practices for all AWS resources. #Bedrock AgentCore MCP Gateway Quickstart

This guide walks through deploying an MCP Gateway, Cognito authorizer, and Lambda tools via the `bedrock_agentcore_starter_toolkit`.

---

## Overview

This quickstart demonstrates how to:

- Set up an AgentCore Gateway with MCP support.
- Initialize a Cognito user pool for secure OAuth-based authentication.
- Add Lambda functions as secure, shareable tools for your agents.

---

## How It Works

### Python Example

```python
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient
import logging

# 1. Initialize GatewayClient
client = GatewayClient(region_name="us-east-1")
client.logger.setLevel(logging.DEBUG)

# 2. Create Cognito authorizer and user pool
cognito_response = client.create_oauth_authorizer_with_cognito("LambdaAuthGW")

# 3. Create the gateway with Cognito integration
gateway = client.create_mcp_gateway(
    authorizer_config=cognito_response["authorizer_config"]
)

# 4. Add a Lambda function as a Gateway target tool
lambda_target = client.create_mcp_gateway_target(gateway=gateway, target_type="lambda")
```

---

## Additional Steps

1. **Automatic Resource Creation:**

   - The toolkit creates an AgentCore Gateway, a Cognito user pool for OAuth, and a sample/test Lambda by default.

2. **Grant Lambda Invoke Permissions:**

   - Every Lambda you wish to connect must allow the Gateway’s IAM role to invoke it.
   - Example policy:
     ```json
     {
       "Effect": "Allow",
       "Principal": {
         "Service": "bedrock.amazonaws.com"
       },
       "Action": "lambda:InvokeFunction",
       "Resource": "<YourLambdaArn>"
     }
     ```
   - Attach this policy using the AWS Console or CLI (`aws lambda add-permission`).

3. **Add More Lambda Tools:**
   - Once permissions are set, use `create_mcp_gateway_target` to register additional Lambdas.

---

## References

- [Amazon Bedrock AgentCore Gateway Documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway.html)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/docs/getting-started/intro)

---

_After setup, your Gateway provides a single, secure MCP endpoint where agents can securely access all registered Lambda tools, with authentication and permission checks enforced by AgentCore and Cognito._
