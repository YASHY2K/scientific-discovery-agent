"""
Utility functions for configuration management.
Supports environment variables and AWS SSM Parameter Store.
"""

import os
import boto3
from botocore.exceptions import ClientError


def get_ssm_parameter(parameter_name: str) -> str | None:
    """
    Fetch a parameter from SSM Parameter Store.

    Args:
        parameter_name: The name/path of the SSM parameter

    Returns:
        The parameter value if found, None otherwise
    """
    try:
        ssm_client = boto3.client("ssm")
        response = ssm_client.get_parameter(Name=parameter_name)
        return response["Parameter"]["Value"]
    except Exception:
        return None


def get_config_value(env_var_name: str, ssm_param_name: str) -> str | None:
    """
    Get configuration value from environment variable or SSM Parameter Store.
    Checks environment variable first, then falls back to SSM.

    Args:
        env_var_name: Name of the environment variable to check
        ssm_param_name: Name/path of the SSM parameter to check if env var not found

    Returns:
        The configuration value if found, None otherwise
    """
    # Check environment variable first
    env_value = os.getenv(env_var_name)
    if env_value is not None:
        return env_value

    # Fall back to SSM Parameter Store
    return get_ssm_parameter(ssm_param_name)
