"""
Shared utility functions for Lambda standardization.
Provides common helper functions for request parsing, response formatting,
error handling, environment variable validation, and logging configuration.
"""

import os
import json
import logging
import sys
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

# Import security and configuration utilities
try:
    from .security_utils import SecurityManager
    from .lambda_config import LambdaConfigManager
except ImportError:
    # Fallback for when modules are not available
    SecurityManager = None
    LambdaConfigManager = None


class LambdaLogger:
    """Standardized logging configuration for Lambda functions."""

    @staticmethod
    def setup_logger(name: str = None, level: str = "INFO") -> logging.Logger:
        """
        Set up standardized logging for Lambda functions.

        Args:
            name: Logger name (defaults to root logger)
            level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

        Returns:
            Configured logger instance
        """
        logger = logging.getLogger(name)

        # Only configure if no handlers exist to avoid duplicate logs
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        # Set level
        log_level = getattr(logging, level.upper(), logging.INFO)
        logger.setLevel(log_level)

        return logger

    @staticmethod
    def log_performance_metrics(
        logger: logging.Logger,
        operation: str,
        duration_ms: float,
        success: bool,
        **additional_metrics,
    ) -> None:
        """
        Log performance metrics in a structured format.

        Args:
            logger: Logger instance
            operation: Name of the operation being measured
            duration_ms: Duration in milliseconds
            success: Whether the operation succeeded
            **additional_metrics: Additional metrics to log
        """
        metrics = {
            "metric_type": "performance",
            "operation": operation,
            "duration_ms": round(duration_ms, 2),
            "success": success,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        # Add any additional metrics
        metrics.update(additional_metrics)

        # Log as structured JSON for easy parsing
        logger.info(f"PERFORMANCE_METRICS: {json.dumps(metrics)}")

    @staticmethod
    def log_structured_error(
        logger: logging.Logger,
        error: Exception,
        operation: str,
        error_category: str = "unknown",
        **context,
    ) -> None:
        """
        Log errors in a structured format with full context.

        Args:
            logger: Logger instance
            error: The exception that occurred
            operation: Name of the operation that failed
            error_category: Category of error (validation, network, aws, etc.)
            **context: Additional context information
        """
        import traceback

        error_data = {
            "error_type": "structured_error",
            "operation": operation,
            "error_category": error_category,
            "exception_type": type(error).__name__,
            "exception_message": str(error),
            "stack_trace": traceback.format_exc(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        # Add context information
        error_data.update(context)

        # Log as structured JSON
        logger.error(f"STRUCTURED_ERROR: {json.dumps(error_data, default=str)}")

    @staticmethod
    def log_operation_start(
        logger: logging.Logger, operation: str, **parameters
    ) -> str:
        """
        Log the start of an operation with parameters.

        Args:
            logger: Logger instance
            operation: Name of the operation starting
            **parameters: Operation parameters to log

        Returns:
            Operation ID for correlation
        """
        import uuid

        operation_id = str(uuid.uuid4())[:8]  # Short ID for correlation

        log_data = {
            "log_type": "operation_start",
            "operation": operation,
            "operation_id": operation_id,
            "parameters": parameters,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        logger.info(f"OPERATION_START: {json.dumps(log_data, default=str)}")
        return operation_id

    @staticmethod
    def log_operation_end(
        logger: logging.Logger,
        operation: str,
        operation_id: str,
        success: bool,
        duration_ms: float,
        **results,
    ) -> None:
        """
        Log the end of an operation with results.

        Args:
            logger: Logger instance
            operation: Name of the operation ending
            operation_id: Operation ID from operation_start
            success: Whether the operation succeeded
            duration_ms: Duration in milliseconds
            **results: Operation results to log
        """
        log_data = {
            "log_type": "operation_end",
            "operation": operation,
            "operation_id": operation_id,
            "success": success,
            "duration_ms": round(duration_ms, 2),
            "results": results,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        logger.info(f"OPERATION_END: {json.dumps(log_data, default=str)}")


class EnvironmentValidator:
    """Environment variable validation utilities."""

    @staticmethod
    def validate_required_vars(required_vars: List[str]) -> Dict[str, str]:
        """
        Validate that all required environment variables are set.

        Args:
            required_vars: List of required environment variable names

        Returns:
            Dictionary of validated environment variables

        Raises:
            ValueError: If any required variable is missing
        """
        config = {}
        missing_vars = []

        for var in required_vars:
            value = os.environ.get(var)
            if not value:
                missing_vars.append(var)
            else:
                config[var] = value

        if missing_vars:
            raise ValueError(
                f"Required environment variables not set: {', '.join(missing_vars)}"
            )

        return config

    @staticmethod
    def get_optional_vars(optional_vars: Dict[str, str]) -> Dict[str, str]:
        """
        Get optional environment variables with defaults.

        Args:
            optional_vars: Dictionary of {var_name: default_value}

        Returns:
            Dictionary of environment variables with values or defaults
        """
        config = {}
        for var, default in optional_vars.items():
            config[var] = os.environ.get(var, default)
        return config

    @staticmethod
    def validate_environment(
        required_vars: List[str] = None, optional_vars: Dict[str, str] = None
    ) -> Dict[str, str]:
        """
        Validate both required and optional environment variables.

        Args:
            required_vars: List of required variable names
            optional_vars: Dictionary of {var_name: default_value}

        Returns:
            Combined configuration dictionary

        Raises:
            ValueError: If any required variable is missing
        """
        config = {}

        if required_vars:
            config.update(EnvironmentValidator.validate_required_vars(required_vars))

        if optional_vars:
            config.update(EnvironmentValidator.get_optional_vars(optional_vars))

        return config


class RequestParser:
    """Request parsing utilities for Lambda functions."""

    @staticmethod
    def parse_event_body(event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse the body from a Lambda event, handling both string and dict formats.

        Args:
            event: Lambda event dictionary

        Returns:
            Parsed body as dictionary

        Raises:
            ValueError: If body is invalid JSON or missing
        """
        body = event.get("body")

        if not body:
            return {}

        if isinstance(body, str):
            try:
                return json.loads(body)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in request body: {e}")
        elif isinstance(body, dict):
            return body
        else:
            raise ValueError("Request body must be JSON string or dictionary")

    @staticmethod
    def validate_required_fields(
        body: Dict[str, Any], required_fields: List[str]
    ) -> None:
        """
        Validate that required fields are present in the request body.

        Args:
            body: Parsed request body
            required_fields: List of required field names

        Raises:
            ValueError: If any required field is missing
        """
        missing_fields = []
        for field in required_fields:
            if field not in body or body[field] is None:
                missing_fields.append(field)

        if missing_fields:
            raise ValueError(
                f"Required fields missing from request: {', '.join(missing_fields)}"
            )


class ResponseFormatter:
    """Response formatting utilities for Lambda functions."""

    @staticmethod
    def create_success_response(
        data: Any, status_code: int = 200, headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Create a standardized success response.

        Args:
            data: Response data to include in body
            status_code: HTTP status code (default: 200)
            headers: Optional response headers

        Returns:
            Formatted Lambda response dictionary
        """
        response = {"statusCode": status_code, "body": json.dumps(data)}

        if headers:
            response["headers"] = headers

        return response

    @staticmethod
    def create_error_response(
        status_code: int,
        error_type: str,
        message: str,
        details: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a standardized error response.

        Args:
            status_code: HTTP status code
            error_type: Error category/type
            message: Human-readable error message
            details: Optional technical details
            headers: Optional response headers

        Returns:
            Formatted Lambda error response dictionary
        """
        error_body = {
            "error": error_type,
            "message": message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        if details:
            error_body["details"] = details

        response = {"statusCode": status_code, "body": json.dumps(error_body)}

        if headers:
            response["headers"] = headers

        return response


class AWSClientManager:
    """AWS client management utilities."""

    _clients = {}

    @classmethod
    def get_client(cls, service_name: str, **kwargs) -> Any:
        """
        Get or create an AWS client, reusing existing clients for efficiency.

        Args:
            service_name: AWS service name (e.g., 's3', 'secretsmanager')
            **kwargs: Additional arguments for boto3.client()

        Returns:
            AWS service client
        """
        client_key = f"{service_name}_{hash(frozenset(kwargs.items()))}"

        if client_key not in cls._clients:
            cls._clients[client_key] = boto3.client(service_name, **kwargs)

        return cls._clients[client_key]

    @staticmethod
    def get_secret(secret_name: str, region_name: str = None) -> Dict[str, Any]:
        """
        Retrieve a secret from AWS Secrets Manager.

        Args:
            secret_name: Name of the secret to retrieve
            region_name: AWS region (optional)

        Returns:
            Secret data as dictionary

        Raises:
            ClientError: If secret retrieval fails
        """
        client = AWSClientManager.get_client("secretsmanager", region_name=region_name)

        try:
            response = client.get_secret_value(SecretId=secret_name)
            return json.loads(response["SecretString"])
        except ClientError as e:
            raise ClientError(
                error_response=e.response, operation_name=e.operation_name
            ) from e


class SecureAPIKeyManager:
    """Secure API key management with multiple retrieval strategies."""

    @classmethod
    def get_api_key(
        cls,
        secret_name: Optional[str] = None,
        env_var_name: Optional[str] = None,
        key_name: str = "api_key",
        required: bool = False,
        logger: Optional[logging.Logger] = None,
    ) -> Optional[str]:
        """
        Securely retrieve API key from multiple sources with fallback.

        Args:
            secret_name: AWS Secrets Manager secret name
            env_var_name: Environment variable name as fallback
            key_name: Key name within the secret JSON
            required: Whether the API key is required
            logger: Logger instance for security events

        Returns:
            API key if found, None otherwise

        Raises:
            ValueError: If required=True and no API key is found
        """
        if logger is None:
            logger = logging.getLogger()

        # Use SecurityManager if available
        if SecurityManager:
            try:
                return SecurityManager.get_api_key_securely(
                    secret_name, env_var_name, key_name, required
                )
            except Exception as e:
                if required:
                    raise
                logger.warning(f"Failed to retrieve API key securely: {e}")
                return None

        # Fallback to basic retrieval
        logger.warning("SecurityManager not available, using basic API key retrieval")

        # Try Secrets Manager first
        if secret_name:
            try:
                secret_data = AWSClientManager.get_secret(secret_name)
                api_key = secret_data.get(key_name)
                if api_key:
                    logger.info(
                        f"Retrieved API key from Secrets Manager: {secret_name}"
                    )
                    return api_key
            except Exception as e:
                logger.warning(f"Failed to retrieve from Secrets Manager: {e}")

        # Try environment variable
        if env_var_name:
            api_key = os.environ.get(env_var_name)
            if api_key:
                logger.info(f"Retrieved API key from environment: {env_var_name}")
                return api_key

        if required:
            raise ValueError("Required API key not found in any configured source")

        return None


class StandardErrorHandler:
    """Standardized error handling for Lambda functions."""

    @staticmethod
    def categorize_http_error(status_code: int) -> tuple[int, str, str]:
        """
        Categorize HTTP errors into appropriate Lambda response codes.

        Args:
            status_code: Original HTTP status code

        Returns:
            Tuple of (lambda_status_code, error_type, category)
        """
        if 400 <= status_code < 500:
            # Client errors - pass through the original status code
            if status_code == 400:
                return 400, "Bad Request", "client_error"
            elif status_code == 401:
                return 401, "Unauthorized", "client_error"
            elif status_code == 403:
                return 403, "Forbidden", "client_error"
            elif status_code == 404:
                return 404, "Not Found", "client_error"
            elif status_code == 429:
                return 429, "Too Many Requests", "client_error"
            else:
                return status_code, "Client Error", "client_error"
        elif 500 <= status_code < 600:
            # Server errors - map to 502 Bad Gateway for external services
            return 502, "Bad Gateway", "server_error"
        else:
            # Unexpected status codes
            return 502, "Bad Gateway", "unknown_error"

    @staticmethod
    def handle_network_timeout() -> Dict[str, Any]:
        """
        Handle network timeout errors with consistent 504 response.

        Returns:
            Standardized 504 Gateway Timeout response
        """
        return ResponseFormatter.create_error_response(
            504,
            "Gateway Timeout",
            "Request timed out while communicating with external service",
            "The external service did not respond within the configured timeout period",
        )

    @staticmethod
    def handle_network_error(
        error: Exception, service_name: str = "external service"
    ) -> Dict[str, Any]:
        """
        Handle general network errors with appropriate categorization.

        Args:
            error: The network exception
            service_name: Name of the service that failed

        Returns:
            Standardized error response
        """
        error_msg = str(error)

        # Check for specific network error types
        if "timeout" in error_msg.lower():
            return StandardErrorHandler.handle_network_timeout()
        elif "connection" in error_msg.lower():
            return ResponseFormatter.create_error_response(
                502, "Bad Gateway", f"Failed to connect to {service_name}", error_msg
            )
        else:
            return ResponseFormatter.create_error_response(
                502,
                "Bad Gateway",
                f"Network error communicating with {service_name}",
                error_msg,
            )

    @staticmethod
    def handle_aws_error(error: ClientError) -> Dict[str, Any]:
        """
        Handle AWS service errors with proper categorization.

        Args:
            error: AWS ClientError exception

        Returns:
            Standardized error response
        """
        error_code = error.response["Error"]["Code"]
        error_message = error.response["Error"]["Message"]

        # Access and permission errors (4xx)
        if error_code in ["AccessDenied", "UnauthorizedOperation", "Forbidden"]:
            return ResponseFormatter.create_error_response(
                403,
                "Access Denied",
                "Insufficient permissions for AWS operation",
                f"{error_code}: {error_message}",
            )

        # Resource not found errors (4xx)
        elif error_code in [
            "ResourceNotFound",
            "NoSuchBucket",
            "NoSuchKey",
            "NoSuchSecret",
        ]:
            return ResponseFormatter.create_error_response(
                404,
                "Resource Not Found",
                "Requested AWS resource not found",
                f"{error_code}: {error_message}",
            )

        # Validation errors (4xx)
        elif error_code in [
            "ValidationException",
            "InvalidParameterValue",
            "InvalidRequest",
        ]:
            return ResponseFormatter.create_error_response(
                400,
                "Validation Error",
                "Invalid request parameters for AWS service",
                f"{error_code}: {error_message}",
            )

        # Rate limiting (4xx)
        elif error_code in [
            "Throttling",
            "ThrottledException",
            "TooManyRequestsException",
        ]:
            return ResponseFormatter.create_error_response(
                429,
                "Too Many Requests",
                "AWS service rate limit exceeded",
                f"{error_code}: {error_message}",
            )

        # Service unavailable (5xx)
        elif error_code in ["ServiceUnavailable", "InternalError", "ServiceFailure"]:
            return ResponseFormatter.create_error_response(
                502,
                "AWS Service Error",
                "AWS service temporarily unavailable",
                f"{error_code}: {error_message}",
            )

        # Default to server error for unknown AWS errors
        else:
            return ResponseFormatter.create_error_response(
                502,
                "AWS Service Error",
                f"AWS service error: {error_code}",
                error_message,
            )

    @staticmethod
    def handle_common_exceptions(func):
        """
        Decorator to handle common Lambda exceptions with standardized responses.

        Args:
            func: Lambda handler function to wrap

        Returns:
            Wrapped function with error handling
        """
        import requests
        from functools import wraps

        @wraps(func)
        def wrapper(event, context):
            logger = logging.getLogger()

            try:
                return func(event, context)

            except ValueError as e:
                LambdaLogger.log_structured_error(
                    logger,
                    e,
                    "lambda_handler",
                    "validation",
                    event_keys=list(event.keys()) if isinstance(event, dict) else None,
                )
                return ResponseFormatter.create_error_response(
                    400, "Validation Error", str(e)
                )

            except requests.exceptions.Timeout as e:
                LambdaLogger.log_structured_error(
                    logger,
                    e,
                    "lambda_handler",
                    "network_timeout",
                    timeout_type="request_timeout",
                )
                return StandardErrorHandler.handle_network_timeout()

            except requests.exceptions.HTTPError as e:
                if e.response is not None:
                    status_code, error_type, category = (
                        StandardErrorHandler.categorize_http_error(
                            e.response.status_code
                        )
                    )
                    LambdaLogger.log_structured_error(
                        logger,
                        e,
                        "lambda_handler",
                        "http_error",
                        status_code=e.response.status_code,
                        error_category=category,
                        response_headers=(
                            dict(e.response.headers) if e.response.headers else None
                        ),
                    )
                    return ResponseFormatter.create_error_response(
                        status_code,
                        error_type,
                        f"HTTP {e.response.status_code} error from external service",
                        str(e),
                    )
                else:
                    LambdaLogger.log_structured_error(
                        logger, e, "lambda_handler", "http_error", has_response=False
                    )
                    return StandardErrorHandler.handle_network_error(
                        e, "external service"
                    )

            except requests.exceptions.ConnectionError as e:
                LambdaLogger.log_structured_error(
                    logger,
                    e,
                    "lambda_handler",
                    "connection_error",
                    error_type="connection_failed",
                )
                return StandardErrorHandler.handle_network_error(e, "external service")

            except requests.exceptions.RequestException as e:
                LambdaLogger.log_structured_error(
                    logger,
                    e,
                    "lambda_handler",
                    "network_error",
                    request_exception_type=type(e).__name__,
                )
                return StandardErrorHandler.handle_network_error(e, "external service")

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                LambdaLogger.log_structured_error(
                    logger,
                    e,
                    "lambda_handler",
                    "aws_error",
                    aws_error_code=error_code,
                    aws_service=e.response.get("ResponseMetadata", {})
                    .get("HTTPHeaders", {})
                    .get("x-amzn-requestid"),
                )
                return StandardErrorHandler.handle_aws_error(e)

            except Exception as e:
                LambdaLogger.log_structured_error(
                    logger,
                    e,
                    "lambda_handler",
                    "unexpected_error",
                    function_name=(
                        func.__name__ if hasattr(func, "__name__") else "unknown"
                    ),
                )
                return ResponseFormatter.create_error_response(
                    500, "Internal Server Error", "An unexpected error occurred", str(e)
                )

        return wrapper


class PerformanceMonitor:
    """Performance monitoring utilities for Lambda functions."""

    @staticmethod
    def monitor_operation(operation_name: str, log_parameters: bool = True):
        """
        Decorator to monitor operation performance and log metrics.

        Args:
            operation_name: Name of the operation being monitored
            log_parameters: Whether to log function parameters

        Returns:
            Decorated function with performance monitoring
        """
        import time
        from functools import wraps

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                logger = logging.getLogger()

                # Log operation start
                parameters = {}
                if log_parameters:
                    # Safely extract parameters (avoid logging sensitive data)
                    try:
                        parameters = {
                            "args_count": len(args),
                            "kwargs_keys": list(kwargs.keys()) if kwargs else [],
                        }
                    except Exception:
                        parameters = {"parameter_extraction_failed": True}

                operation_id = LambdaLogger.log_operation_start(
                    logger, operation_name, **parameters
                )

                start_time = time.time()
                success = False
                result = None
                error = None

                try:
                    result = func(*args, **kwargs)
                    success = True
                    return result

                except Exception as e:
                    error = e
                    success = False
                    raise

                finally:
                    # Calculate duration
                    duration_ms = (time.time() - start_time) * 1000

                    # Log performance metrics
                    additional_metrics = {}
                    if hasattr(result, "__len__"):
                        try:
                            additional_metrics["result_size"] = len(result)
                        except Exception:
                            pass

                    LambdaLogger.log_performance_metrics(
                        logger,
                        operation_name,
                        duration_ms,
                        success,
                        **additional_metrics,
                    )

                    # Log operation end
                    end_results = {}
                    if error:
                        end_results["error_type"] = type(error).__name__

                    LambdaLogger.log_operation_end(
                        logger,
                        operation_name,
                        operation_id,
                        success,
                        duration_ms,
                        **end_results,
                    )

            return wrapper

        return decorator


# Convenience function for complete Lambda setup
def setup_lambda_environment(
    required_env_vars: List[str] = None,
    optional_env_vars: Dict[str, str] = None,
    logger_name: str = None,
    log_level: str = "INFO",
) -> tuple[Dict[str, str], logging.Logger]:
    """
    Complete Lambda environment setup with validation and logging.

    Args:
        required_env_vars: List of required environment variable names
        optional_env_vars: Dictionary of {var_name: default_value}
        logger_name: Logger name (defaults to root logger)
        log_level: Logging level

    Returns:
        Tuple of (config_dict, logger)

    Raises:
        ValueError: If required environment variables are missing
    """
    # Setup logging
    logger = LambdaLogger.setup_logger(logger_name, log_level)

    # Validate environment
    config = EnvironmentValidator.validate_environment(
        required_env_vars, optional_env_vars
    )

    logger.info("Lambda environment setup completed successfully")
    return config, logger


def setup_secure_lambda_environment(
    required_env_vars: List[str] = None,
    optional_env_vars: Dict[str, str] = None,
    function_name: str = "lambda_function",
    log_level: str = "INFO",
) -> tuple[Dict[str, str], logging.Logger]:
    """
    Set up Lambda environment with enhanced security validation and logging.

    Args:
        required_env_vars: List of required environment variable names
        optional_env_vars: Dict of optional vars with default values
        function_name: Function name for security context
        log_level: Logging level

    Returns:
        Tuple of (config_dict, logger)

    Raises:
        ValueError: If validation fails or security requirements are not met
    """
    # Setup logging first
    logger = LambdaLogger.setup_logger(level=log_level)

    # Use SecurityManager for enhanced validation if available
    if SecurityManager:
        try:
            config = SecurityManager.validate_environment_startup(
                required_env_vars or [], optional_env_vars or {}, function_name
            )

            # Log security event
            SecurityManager.log_security_event(
                logger,
                "environment_validation_success",
                {"function_name": function_name, "config_keys": list(config.keys())},
            )

            return config, logger

        except Exception as e:
            # Log security event for validation failure
            SecurityManager.log_security_event(
                logger,
                "environment_validation_failure",
                {"function_name": function_name, "error": str(e)},
                level="ERROR",
            )
            raise
    else:
        # Fallback to basic validation
        logger.warning("SecurityManager not available, using basic validation")
        return setup_lambda_environment(
            required_env_vars, optional_env_vars, None, log_level
        )
