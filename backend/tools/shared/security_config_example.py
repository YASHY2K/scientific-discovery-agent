"""
Example of secure Lambda function configuration using the security utilities.
This demonstrates best practices for API key management, environment validation,
and secure logging in AWS Lambda functions.
"""

import os
import json
import logging
from typing import Dict, Any, Optional

# Import shared utilities
from lambda_utils import (
    setup_secure_lambda_environment,
    SecureAPIKeyManager,
    ResponseFormatter,
    StandardErrorHandler,
)
from security_utils import SecurityManager


def secure_lambda_handler_example(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Example Lambda handler demonstrating secure configuration practices.

    This example shows how to:
    1. Validate environment variables securely at startup
    2. Retrieve API keys from multiple sources with fallback
    3. Sanitize logging to prevent sensitive data exposure
    4. Handle errors with proper security context
    """

    # Define environment configuration with security in mind
    REQUIRED_ENV_VARS = [
        "API_BASE_URL",  # Required API endpoint
        "S3_BUCKET_NAME",  # Required S3 bucket
    ]

    OPTIONAL_ENV_VARS = {
        "API_TIMEOUT_SECONDS": "30",
        "MAX_RETRIES": "3",
        "LOG_LEVEL": "INFO",
        "SECRET_NAME": "",  # Optional Secrets Manager secret name
        "API_KEY_ENV_VAR": "",  # Optional environment variable for API key
    }

    try:
        # Secure environment setup with comprehensive validation
        config, logger = setup_secure_lambda_environment(
            required_env_vars=REQUIRED_ENV_VARS,
            optional_env_vars=OPTIONAL_ENV_VARS,
            function_name="secure_example_function",
            log_level=OPTIONAL_ENV_VARS["LOG_LEVEL"],
        )

        # Secure API key retrieval with multiple fallback options
        api_key = SecureAPIKeyManager.get_api_key(
            secret_name=config.get("SECRET_NAME") or None,
            env_var_name=config.get("API_KEY_ENV_VAR") or None,
            key_name="SEMANTIC_SCHOLAR_API_KEY",  # Key name in Secrets Manager
            required=False,  # Set to True if API key is mandatory
            logger=logger,
        )

        # Log security event for API key status (without exposing the key)
        SecurityManager.log_security_event(
            logger,
            "api_key_retrieval",
            {
                "has_api_key": api_key is not None,
                "source": (
                    "secrets_manager" if config.get("SECRET_NAME") else "environment"
                ),
                "function_name": "secure_example_function",
            },
        )

        # Validate URLs for security
        api_base_url = config["API_BASE_URL"]
        if not SecurityManager.validate_url_security(api_base_url, {"https"}):
            raise ValueError(f"Insecure API URL: {api_base_url}")

        # Create secure headers for API requests
        headers = SecurityManager.create_secure_headers(api_key)

        # Log sanitized configuration (sensitive values are redacted)
        sanitized_config = SecurityManager.sanitize_for_logging(config)
        logger.info(f"Function configuration: {json.dumps(sanitized_config)}")

        # Example business logic would go here
        # For demonstration, we'll just return success

        result = {
            "status": "success",
            "message": "Secure Lambda function executed successfully",
            "has_api_key": api_key is not None,
            "config_validated": True,
        }

        return ResponseFormatter.create_success_response(result)

    except ValueError as e:
        # Log security-related validation errors
        logger.error(f"Security validation failed: {e}")
        SecurityManager.log_security_event(
            logging.getLogger(),
            "security_validation_error",
            {"error": str(e), "function_name": "secure_example_function"},
            level="ERROR",
        )
        return ResponseFormatter.create_error_response(
            400, "Security Validation Error", str(e)
        )

    except Exception as e:
        # Log unexpected errors with security context
        logger.exception("Unexpected error in secure Lambda function")
        SecurityManager.log_security_event(
            logging.getLogger(),
            "unexpected_error",
            {
                "error_type": type(e).__name__,
                "function_name": "secure_example_function",
            },
            level="ERROR",
        )
        return ResponseFormatter.create_error_response(
            500, "Internal Server Error", "An unexpected error occurred"
        )


# Example of secure environment variable configuration
SECURE_ENV_CONFIG_EXAMPLE = {
    # Required variables (function will fail if not set)
    "API_BASE_URL": "https://api.semanticscholar.org/graph/v1",
    "S3_BUCKET_NAME": "my-research-bucket",
    # Optional variables with secure defaults
    "API_TIMEOUT_SECONDS": "30",
    "MAX_RETRIES": "3",
    "LOG_LEVEL": "INFO",
    # Security-related configuration
    "SECRET_NAME": "research-agent/api-keys",  # Secrets Manager secret name
    "API_KEY_ENV_VAR": "SEMANTIC_SCHOLAR_API_KEY",  # Fallback env var
    # AWS Lambda automatically provides these
    "AWS_REGION": "us-east-1",
    "AWS_LAMBDA_FUNCTION_NAME": "research-agent-secure-example",
}


# Example Secrets Manager secret structure
SECRETS_MANAGER_EXAMPLE = {
    "secret_name": "research-agent/api-keys",
    "secret_value": {
        "SEMANTIC_SCHOLAR_API_KEY": "your-actual-api-key-here",
        "ARXIV_API_KEY": "optional-arxiv-key",
        "OTHER_SERVICE_KEY": "another-service-key",
    },
}


def create_secure_lambda_deployment_config():
    """
    Generate secure deployment configuration for Lambda functions.

    Returns:
        Dictionary with secure Lambda configuration
    """
    return {
        "function_configuration": {
            "memory_mb": 512,
            "timeout_seconds": 60,
            "environment_variables": {
                # Only non-sensitive configuration in environment
                "API_BASE_URL": "https://api.semanticscholar.org/graph/v1",
                "API_TIMEOUT_SECONDS": "30",
                "MAX_RETRIES": "3",
                "LOG_LEVEL": "INFO",
                "SECRET_NAME": "research-agent/api-keys",  # Reference to secret
                # Never put actual API keys in environment variables in production
            },
            "iam_permissions": [
                "secretsmanager:GetSecretValue",  # For API key retrieval
                "s3:GetObject",
                "s3:PutObject",
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
            ],
        },
        "security_best_practices": {
            "use_secrets_manager": True,
            "validate_environment_startup": True,
            "sanitize_logs": True,
            "validate_urls": True,
            "use_https_only": True,
            "implement_retry_logic": True,
            "log_security_events": True,
        },
    }
