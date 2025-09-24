"""
Example usage of shared Lambda utilities.
This demonstrates how to use the standardized utilities in a Lambda function.
"""

import json
from typing import Dict, Any

# Import shared utilities
from .lambda_utils import (
    setup_lambda_environment,
    RequestParser,
    ResponseFormatter,
    StandardErrorHandler,
    AWSClientManager,
)

# Define environment configuration
REQUIRED_ENV_VARS = ["BUCKET_NAME"]
OPTIONAL_ENV_VARS = {"TIMEOUT": "30", "SEARCH_LIMIT": "10", "LOG_LEVEL": "INFO"}

# Setup environment (done outside handler for reuse)
config, logger = setup_lambda_environment(
    required_env_vars=REQUIRED_ENV_VARS,
    optional_env_vars=OPTIONAL_ENV_VARS,
    log_level=OPTIONAL_ENV_VARS["LOG_LEVEL"],
)

# Initialize AWS clients outside handler for reuse
s3_client = AWSClientManager.get_client("s3")


@StandardErrorHandler.handle_common_exceptions
def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Example Lambda handler using standardized utilities.

    Args:
        event: Lambda event dictionary
        context: Lambda context object

    Returns:
        Standardized Lambda response
    """
    logger.info(f"Received event: {json.dumps(event)}")

    # Parse and validate request
    body = RequestParser.parse_event_body(event)
    RequestParser.validate_required_fields(body, ["query"])

    # Extract parameters
    query = body["query"]
    limit = int(body.get("limit", config["SEARCH_LIMIT"]))

    logger.info(f"Processing query: {query} with limit: {limit}")

    # Execute tool-specific logic
    result = execute_tool_logic(query, limit)

    # Return success response
    return ResponseFormatter.create_success_response(
        {
            "query": query,
            "results": result,
            "metadata": {"limit": limit, "count": len(result)},
        }
    )


def execute_tool_logic(query: str, limit: int) -> list:
    """
    Example tool-specific logic.
    Replace this with actual tool implementation.
    """
    # This is where you would implement the actual tool functionality
    # For example: search ArXiv, download papers, extract content, etc.

    logger.info(f"Executing tool logic for query: {query}")

    # Example implementation
    results = []
    for i in range(min(limit, 3)):  # Mock results
        results.append(
            {
                "id": f"result_{i}",
                "title": f"Mock result {i} for query: {query}",
                "score": 0.9 - (i * 0.1),
            }
        )

    return results


# Alternative handler without decorator (manual error handling)
def lambda_handler_manual(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Example Lambda handler with manual error handling.
    Use this approach if you need custom error handling logic.
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        # Parse and validate request
        body = RequestParser.parse_event_body(event)
        RequestParser.validate_required_fields(body, ["query"])

        # Extract parameters
        query = body["query"]

        # Execute tool logic
        result = execute_tool_logic(query, int(config["SEARCH_LIMIT"]))

        # Return success response
        return ResponseFormatter.create_success_response(result)

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return ResponseFormatter.create_error_response(400, "Validation Error", str(e))
    except Exception as e:
        logger.exception("Unexpected error")
        return ResponseFormatter.create_error_response(
            500, "Internal Server Error", "An unexpected error occurred", str(e)
        )


# Example of using AWS clients
def example_s3_operation(bucket_name: str, key: str) -> Dict[str, Any]:
    """
    Example S3 operation using the standardized client manager.
    """
    try:
        # Use the pre-initialized client
        response = s3_client.head_object(Bucket=bucket_name, Key=key)

        return {
            "exists": True,
            "size": response.get("ContentLength", 0),
            "last_modified": (
                response.get("LastModified").isoformat()
                if response.get("LastModified")
                else None
            ),
        }
    except s3_client.exceptions.NoSuchKey:
        return {"exists": False}


# Example of retrieving secrets
def example_secret_retrieval(secret_name: str) -> str:
    """
    Example of retrieving API keys from Secrets Manager.
    """
    try:
        secret_data = AWSClientManager.get_secret(secret_name)
        api_key = secret_data.get("API_KEY")

        if not api_key:
            logger.warning(f"API_KEY not found in secret {secret_name}")
            return None

        logger.info("Successfully retrieved API key from Secrets Manager")
        return api_key

    except Exception as e:
        logger.error(f"Failed to retrieve secret {secret_name}: {e}")
        return None
