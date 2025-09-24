"""
Security utilities for Lambda functions to handle API keys, secrets, and secure logging.
Implements secure handling of sensitive information and environment validation.
"""

import os
import json
import logging
import re
from typing import Dict, Any, Optional, List, Set
from functools import lru_cache
import boto3
from botocore.exceptions import ClientError


class SecurityManager:
    """
    Centralized security management for Lambda functions.
    Handles secure API key retrieval, environment validation, and logging sanitization.
    """

    # Cache for secrets to avoid repeated API calls
    _secrets_cache: Dict[str, Dict[str, Any]] = {}

    # Sensitive patterns that should never be logged
    SENSITIVE_PATTERNS = {
        r"api[_-]?key",
        r"secret",
        r"password",
        r"token",
        r"credential",
        r"auth",
        r"bearer",
        r"x-api-key",
    }

    @classmethod
    def get_api_key_securely(
        cls,
        secret_name: Optional[str] = None,
        env_var_name: Optional[str] = None,
        key_name: str = "api_key",
        required: bool = False,
    ) -> Optional[str]:
        """
        Securely retrieve API key from Secrets Manager or environment variables.

        Args:
            secret_name: AWS Secrets Manager secret name
            env_var_name: Environment variable name as fallback
            key_name: Key name within the secret JSON
            required: Whether the API key is required

        Returns:
            API key if found, None otherwise

        Raises:
            ValueError: If required=True and no API key is found
        """
        logger = logging.getLogger()

        # Try Secrets Manager first if secret_name is provided
        if secret_name:
            try:
                api_key = cls._get_secret_value(secret_name, key_name)
                if api_key:
                    logger.info(
                        f"Successfully retrieved API key from Secrets Manager: {secret_name}"
                    )
                    return api_key
                else:
                    logger.warning(
                        f"API key '{key_name}' not found in secret '{secret_name}'"
                    )
            except Exception as e:
                logger.warning(f"Failed to retrieve API key from Secrets Manager: {e}")

        # Fallback to environment variable
        if env_var_name:
            api_key = os.environ.get(env_var_name)
            if api_key:
                logger.info(
                    f"Retrieved API key from environment variable: {env_var_name}"
                )
                return api_key
            else:
                logger.warning(
                    f"API key not found in environment variable: {env_var_name}"
                )

        # Handle required API key
        if required:
            sources = []
            if secret_name:
                sources.append(f"Secrets Manager ({secret_name})")
            if env_var_name:
                sources.append(f"Environment ({env_var_name})")

            raise ValueError(
                f"Required API key not found in any configured source: {', '.join(sources)}"
            )

        logger.info("No API key configured - proceeding without authentication")
        return None

    @classmethod
    def _get_secret_value(cls, secret_name: str, key_name: str) -> Optional[str]:
        """
        Retrieve a specific value from AWS Secrets Manager with caching.

        Args:
            secret_name: Name of the secret
            key_name: Key within the secret JSON

        Returns:
            Secret value if found, None otherwise
        """
        # Check cache first
        cache_key = f"{secret_name}:{key_name}"
        if cache_key in cls._secrets_cache:
            return cls._secrets_cache[cache_key]

        try:
            # Get AWS client with optimized configuration
            secrets_client = boto3.client(
                "secretsmanager",
                config=boto3.session.Config(
                    retries={"max_attempts": 3, "mode": "adaptive"},
                    connect_timeout=5,
                    read_timeout=10,
                ),
            )

            response = secrets_client.get_secret_value(SecretId=secret_name)
            secret_data = json.loads(response["SecretString"])

            value = secret_data.get(key_name)

            # Cache the result
            cls._secrets_cache[cache_key] = value

            return value

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "ResourceNotFoundException":
                raise ValueError(f"Secret '{secret_name}' not found")
            elif error_code == "AccessDeniedException":
                raise ValueError(f"Access denied to secret '{secret_name}'")
            else:
                raise ValueError(
                    f"Failed to retrieve secret '{secret_name}': {error_code}"
                )
        except json.JSONDecodeError:
            raise ValueError(f"Secret '{secret_name}' does not contain valid JSON")
        except Exception as e:
            raise ValueError(f"Unexpected error retrieving secret '{secret_name}': {e}")

    @classmethod
    def validate_environment_startup(
        cls, required_vars: List[str], optional_vars: Dict[str, str], function_name: str
    ) -> Dict[str, str]:
        """
        Comprehensive environment validation at Lambda startup with security checks.

        Args:
            required_vars: List of required environment variable names
            optional_vars: Dict of optional variables with default values
            function_name: Function name for logging context

        Returns:
            Validated configuration dictionary

        Raises:
            ValueError: If validation fails
        """
        logger = logging.getLogger()
        config = {}
        validation_errors = []

        # Validate required variables
        for var in required_vars:
            value = os.environ.get(var)
            if not value:
                validation_errors.append(
                    f"Required environment variable '{var}' is not set"
                )
            elif cls._is_potentially_sensitive(var) and len(value.strip()) < 8:
                validation_errors.append(
                    f"Environment variable '{var}' appears to be too short for a secure value"
                )
            else:
                config[var] = value.strip()

        # Set optional variables with validation
        for var, default in optional_vars.items():
            value = os.environ.get(var, default).strip()

            # Validate specific variable types
            if var.endswith("_TIMEOUT") or var.endswith("_TIMEOUT_SECONDS"):
                try:
                    timeout_val = int(value)
                    if timeout_val <= 0 or timeout_val > 900:  # Max 15 minutes
                        validation_errors.append(
                            f"Timeout variable '{var}' must be between 1 and 900 seconds"
                        )
                except ValueError:
                    validation_errors.append(
                        f"Timeout variable '{var}' must be a valid integer"
                    )

            elif var.endswith("_LIMIT"):
                try:
                    limit_val = int(value)
                    if limit_val <= 0 or limit_val > 1000:
                        validation_errors.append(
                            f"Limit variable '{var}' must be between 1 and 1000"
                        )
                except ValueError:
                    validation_errors.append(
                        f"Limit variable '{var}' must be a valid integer"
                    )

            elif var.endswith("_SIZE_MB"):
                try:
                    size_val = int(value)
                    if size_val <= 0 or size_val > 10000:  # Max 10GB
                        validation_errors.append(
                            f"Size variable '{var}' must be between 1 and 10000 MB"
                        )
                except ValueError:
                    validation_errors.append(
                        f"Size variable '{var}' must be a valid integer"
                    )

            config[var] = value

        # Check for common security misconfigurations
        cls._validate_security_configuration(config, validation_errors)

        if validation_errors:
            error_msg = (
                f"Environment validation failed for {function_name}:\n"
                + "\n".join(validation_errors)
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Log sanitized configuration
        sanitized_config = cls.sanitize_for_logging(config)
        logger.info(
            f"Environment validation successful for {function_name}: {json.dumps(sanitized_config)}"
        )

        return config

    @classmethod
    def _validate_security_configuration(
        cls, config: Dict[str, str], errors: List[str]
    ) -> None:
        """
        Validate security-related configuration settings.

        Args:
            config: Configuration dictionary
            errors: List to append validation errors to
        """
        # Check for insecure defaults
        insecure_patterns = {
            "localhost": "Should not use localhost in production",
            "127.0.0.1": "Should not use localhost IP in production",
            "http://": "Should use HTTPS for external APIs",
            "test": "Should not use test values in production",
            "demo": "Should not use demo values in production",
            "example": "Should not use example values in production",
        }

        for key, value in config.items():
            value_lower = value.lower()
            for pattern, message in insecure_patterns.items():
                if pattern in value_lower and not cls._is_development_environment():
                    errors.append(f"Potentially insecure value in '{key}': {message}")

    @classmethod
    def _is_development_environment(cls) -> bool:
        """Check if running in development environment."""
        env_indicators = ["dev", "development", "local", "test"]
        aws_env = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "").lower()
        return any(indicator in aws_env for indicator in env_indicators)

    @classmethod
    def _is_potentially_sensitive(cls, var_name: str) -> bool:
        """Check if a variable name suggests it contains sensitive information."""
        var_lower = var_name.lower()
        return any(
            pattern in var_lower
            for pattern in ["key", "secret", "password", "token", "credential"]
        )

    @classmethod
    def sanitize_for_logging(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize data structure for safe logging by redacting sensitive information.

        Args:
            data: Dictionary that may contain sensitive information

        Returns:
            Sanitized dictionary safe for logging
        """
        if not isinstance(data, dict):
            return data

        sanitized = {}

        for key, value in data.items():
            key_lower = key.lower()

            # Check if key suggests sensitive content
            is_sensitive = any(
                re.search(pattern, key_lower, re.IGNORECASE)
                for pattern in cls.SENSITIVE_PATTERNS
            )

            if is_sensitive:
                if isinstance(value, str) and value:
                    # Show first 2 and last 2 characters for debugging
                    if len(value) > 8:
                        sanitized[key] = f"{value[:2]}***{value[-2:]}"
                    else:
                        sanitized[key] = "[REDACTED]"
                else:
                    sanitized[key] = "[NOT_SET]"
            elif isinstance(value, dict):
                sanitized[key] = cls.sanitize_for_logging(value)
            else:
                sanitized[key] = value

        return sanitized

    @classmethod
    def validate_url_security(cls, url: str, allowed_schemes: Set[str] = None) -> bool:
        """
        Validate URL for security concerns.

        Args:
            url: URL to validate
            allowed_schemes: Set of allowed URL schemes (default: https, http)

        Returns:
            True if URL is considered secure, False otherwise
        """
        if not url or not isinstance(url, str):
            return False

        if allowed_schemes is None:
            allowed_schemes = {"https", "http"}

        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)

            # Check scheme
            if parsed.scheme not in allowed_schemes:
                return False

            # Check for localhost/private IPs in production
            if not cls._is_development_environment():
                hostname = parsed.hostname
                if hostname:
                    hostname_lower = hostname.lower()
                    if (
                        hostname_lower in ["localhost", "127.0.0.1"]
                        or hostname_lower.startswith("192.168.")
                        or hostname_lower.startswith("10.")
                        or hostname_lower.startswith("172.")
                    ):
                        return False

            return True

        except Exception:
            return False

    @classmethod
    def create_secure_headers(cls, api_key: Optional[str] = None) -> Dict[str, str]:
        """
        Create secure HTTP headers for API requests.

        Args:
            api_key: Optional API key to include in headers

        Returns:
            Dictionary of secure HTTP headers
        """
        headers = {
            "User-Agent": "AWS-Lambda-Research-Agent/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if api_key:
            headers["x-api-key"] = api_key

        return headers

    @classmethod
    def log_security_event(
        cls,
        logger: logging.Logger,
        event_type: str,
        details: Dict[str, Any],
        level: str = "INFO",
    ) -> None:
        """
        Log security-related events with proper sanitization.

        Args:
            logger: Logger instance
            event_type: Type of security event
            details: Event details (will be sanitized)
            level: Log level (INFO, WARNING, ERROR)
        """
        sanitized_details = cls.sanitize_for_logging(details)

        log_entry = {
            "event_type": event_type,
            "timestamp": json.dumps(
                __import__("datetime").datetime.utcnow().isoformat() + "Z"
            ).strip('"'),
            "details": sanitized_details,
        }

        log_message = f"Security event: {json.dumps(log_entry)}"

        if level.upper() == "ERROR":
            logger.error(log_message)
        elif level.upper() == "WARNING":
            logger.warning(log_message)
        else:
            logger.info(log_message)
