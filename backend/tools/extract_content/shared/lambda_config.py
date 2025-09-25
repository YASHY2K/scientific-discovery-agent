"""
Lambda configuration management utilities for optimized performance and security.
Handles memory allocation, timeouts, AWS client reuse, and environment validation.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from functools import lru_cache
import boto3
from botocore.config import Config


class LambdaConfigManager:
    """
    Centralized configuration management for Lambda functions with performance optimization.
    """

    # AWS client instances (reused across invocations)
    _clients: Dict[str, Any] = {}
    _config_cache: Dict[str, Any] = {}

    @classmethod
    @lru_cache(maxsize=1)
    def get_aws_config(cls) -> Config:
        """
        Get optimized AWS client configuration for Lambda environment.

        Returns:
            Boto3 Config object with optimized settings
        """
        return Config(
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            retries={"max_attempts": 3, "mode": "adaptive"},
            max_pool_connections=50,  # Optimize for concurrent requests
            connect_timeout=5,
            read_timeout=30,
        )

    @classmethod
    def get_client(cls, service_name: str, **kwargs) -> Any:
        """
        Get or create AWS service client with reuse across invocations.

        Args:
            service_name: AWS service name (e.g., 's3', 'secretsmanager')
            **kwargs: Additional client configuration

        Returns:
            AWS service client instance
        """
        client_key = f"{service_name}_{hash(str(sorted(kwargs.items())))}"

        if client_key not in cls._clients:
            config = cls.get_aws_config()
            cls._clients[client_key] = boto3.client(
                service_name, config=config, **kwargs
            )

        return cls._clients[client_key]

    @classmethod
    def validate_environment_variables(
        cls,
        required_vars: List[str],
        optional_vars: Dict[str, str],
        function_name: str = "lambda_function",
    ) -> Dict[str, str]:
        """
        Validate and return environment configuration with security checks.

        Args:
            required_vars: List of required environment variable names
            optional_vars: Dict of optional vars with default values
            function_name: Function name for logging context

        Returns:
            Dictionary of validated environment configuration

        Raises:
            ValueError: If required variables are missing or invalid
        """
        config = {}
        missing_vars = []

        # Validate required variables
        for var in required_vars:
            value = os.environ.get(var)
            if not value:
                missing_vars.append(var)
            else:
                config[var] = value

        if missing_vars:
            raise ValueError(
                f"Missing required environment variables for {function_name}: "
                f"{', '.join(missing_vars)}"
            )

        # Set optional variables with defaults
        for var, default in optional_vars.items():
            config[var] = os.environ.get(var, default)

        # Validate numeric configurations
        cls._validate_numeric_configs(config, function_name)

        # Cache configuration
        cls._config_cache[function_name] = config

        return config

    @classmethod
    def _validate_numeric_configs(
        cls, config: Dict[str, str], function_name: str
    ) -> None:
        """
        Validate numeric configuration values.

        Args:
            config: Configuration dictionary
            function_name: Function name for error context

        Raises:
            ValueError: If numeric values are invalid
        """
        numeric_validations = {
            "TIMEOUT": (1, 900),  # 1 second to 15 minutes
            "HTTP_TIMEOUT_SECONDS": (1, 300),  # 1 second to 5 minutes
            "SEARCH_LIMIT": (1, 100),  # Reasonable search limits
            "CHUNK_SIZE": (100, 10000),  # Text chunking limits
            "CHUNK_OVERLAP": (0, 1000),  # Overlap limits
            "MAX_FILE_SIZE_MB": (1, 1000),  # File size limits
        }

        for var, (min_val, max_val) in numeric_validations.items():
            if var in config:
                try:
                    value = int(config[var])
                    if not (min_val <= value <= max_val):
                        raise ValueError(
                            f"{var} must be between {min_val} and {max_val}, got {value}"
                        )
                except ValueError as e:
                    if "invalid literal" in str(e):
                        raise ValueError(
                            f"{var} must be a valid integer, got '{config[var]}'"
                        )
                    raise

    @classmethod
    def get_memory_recommendations(cls) -> Dict[str, Dict[str, Any]]:
        """
        Get memory allocation recommendations for different Lambda function types.

        Returns:
            Dictionary of function types with memory and timeout recommendations
        """
        return {
            "api_lightweight": {
                "memory_mb": 256,
                "timeout_seconds": 30,
                "description": "For simple API calls and lightweight processing",
            },
            "file_processing": {
                "memory_mb": 1024,
                "timeout_seconds": 180,
                "description": "For file downloads, uploads, and moderate processing",
            },
            "pdf_processing": {
                "memory_mb": 2048,
                "timeout_seconds": 300,
                "description": "For PDF text extraction and memory-intensive operations",
            },
            "text_processing": {
                "memory_mb": 1024,
                "timeout_seconds": 120,
                "description": "For text cleaning, chunking, and NLP operations",
            },
        }

    @classmethod
    def log_performance_metrics(
        cls,
        logger: logging.Logger,
        function_name: str,
        execution_time_ms: float,
        memory_used_mb: Optional[float] = None,
    ) -> None:
        """
        Log performance metrics for monitoring and optimization.

        Args:
            logger: Logger instance
            function_name: Name of the function
            execution_time_ms: Execution time in milliseconds
            memory_used_mb: Memory used in MB (if available)
        """
        metrics = {
            "function_name": function_name,
            "execution_time_ms": round(execution_time_ms, 2),
            "timestamp": json.dumps(
                __import__("datetime").datetime.utcnow().isoformat() + "Z"
            ).strip('"'),
        }

        if memory_used_mb:
            metrics["memory_used_mb"] = round(memory_used_mb, 2)

        logger.info(f"Performance metrics: {json.dumps(metrics)}")

    @classmethod
    def validate_s3_configuration(
        cls, bucket_name: str, operation: str = "read"
    ) -> bool:
        """
        Validate S3 bucket access and configuration.

        Args:
            bucket_name: S3 bucket name to validate
            operation: Type of operation ('read', 'write', 'both')

        Returns:
            True if bucket is accessible, False otherwise
        """
        try:
            s3_client = cls.get_client("s3")

            # Check if bucket exists and is accessible
            s3_client.head_bucket(Bucket=bucket_name)

            if operation in ["write", "both"]:
                # Test write permissions with a small test object
                test_key = "config_validation_test"
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=test_key,
                    Body=b"test",
                    Metadata={"purpose": "config_validation"},
                )
                # Clean up test object
                s3_client.delete_object(Bucket=bucket_name, Key=test_key)

            return True

        except Exception as e:
            logging.getLogger().error(
                f"S3 configuration validation failed for {bucket_name}: {e}"
            )
            return False

    @classmethod
    def get_secrets_manager_value(cls, secret_name: str, key: str) -> Optional[str]:
        """
        Securely retrieve value from AWS Secrets Manager with caching.

        Args:
            secret_name: Name of the secret in Secrets Manager
            key: Key within the secret JSON

        Returns:
            Secret value if found, None otherwise
        """
        cache_key = f"secret_{secret_name}_{key}"

        if cache_key in cls._config_cache:
            return cls._config_cache[cache_key]

        try:
            secrets_client = cls.get_client("secretsmanager")
            response = secrets_client.get_secret_value(SecretId=secret_name)

            secret_data = json.loads(response["SecretString"])
            value = secret_data.get(key)

            # Cache the value (but don't log it)
            cls._config_cache[cache_key] = value

            return value

        except Exception as e:
            logging.getLogger().warning(
                f"Failed to retrieve secret {secret_name}.{key}: {e}"
            )
            return None

    @classmethod
    def ensure_no_sensitive_logging(cls, config: Dict[str, str]) -> Dict[str, str]:
        """
        Create a sanitized version of configuration for logging.

        Args:
            config: Original configuration dictionary

        Returns:
            Sanitized configuration safe for logging
        """
        sensitive_keys = {
            "API_KEY",
            "SECRET",
            "PASSWORD",
            "TOKEN",
            "CREDENTIAL",
            "SEMANTIC_SCHOLAR_API_KEY",
            "SECRET_NAME",
        }

        sanitized = {}
        for key, value in config.items():
            if any(sensitive in key.upper() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]" if value else "[NOT_SET]"
            else:
                sanitized[key] = value

        return sanitized
