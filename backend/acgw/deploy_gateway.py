from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient
import logging

# setup the client
client = GatewayClient(region_name="us-east-1")
client.logger.setLevel(logging.DEBUG)

# create cognito authorizer
cognito_response = client.create_oauth_authorizer_with_cognito("LambdaAuthGW")

# create the gateway
gateway = client.create_mcp_gateway(
    authorizer_config=cognito_response["authorizer_config"]
)

# create a lambda target
lambda_target = client.create_mcp_gateway_target(gateway=gateway, target_type="lambda")
