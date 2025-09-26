import os
import json
import logging
import requests
from requests.exceptions import RequestException, Timeout
from typing import Dict, Any, Optional
import sys
import time
from functools import wraps

sys.path.append("/opt/python")
from shared.lambda_utils import (
    setup_secure_lambda_environment,
    SecureAPIKeyManager,
    RequestParser,
    ResponseFormatter,
    AWSClientManager,
    StandardErrorHandler,
    PerformanceMonitor,
    LambdaLogger,
)

# Import security utilities with fallback
try:
    from shared.security_utils import SecurityManager
except ImportError:
    SecurityManager = None

# Environment configuration
REQUIRED_ENV_VARS = []  # No required vars - can work without API key
OPTIONAL_ENV_VARS = {
    "SEMANTIC_SCHOLAR_BASE": "https://api.semanticscholar.org/graph/v1",
    "SEARCH_LIMIT": "3",
    "HTTP_TIMEOUT_SECONDS": "5",
    "SECRET_NAME": "SEMANTIC_SCHOLAR_API_KEY",
    "LOG_LEVEL": "INFO",
}

# Initialize environment and logging with enhanced security
config, logger = setup_secure_lambda_environment(
    required_env_vars=REQUIRED_ENV_VARS,
    optional_env_vars=OPTIONAL_ENV_VARS,
    function_name="search_semantic_scholar",
    log_level="INFO",
)

# Parse configuration values
SEMANTIC_SCHOLAR_BASE = config["SEMANTIC_SCHOLAR_BASE"]
SEARCH_LIMIT = int(config["SEARCH_LIMIT"])
TIMEOUT = float(config["HTTP_TIMEOUT_SECONDS"])
SECRET_NAME = config["SECRET_NAME"]

# Validate API base URL for security
if SecurityManager and not SecurityManager.validate_url_security(
    SEMANTIC_SCHOLAR_BASE, {"https"}
):
    logger.warning(f"API base URL may not be secure: {SEMANTIC_SCHOLAR_BASE}")

# Secure API key retrieval with multiple fallback options
API_KEY = SecureAPIKeyManager.get_api_key(
    secret_name=SECRET_NAME if SECRET_NAME else None,
    env_var_name="SEMANTIC_SCHOLAR_API_KEY",  # Fallback environment variable
    key_name="SEMANTIC_SCHOLAR_API_KEY",
    required=False,
    logger=logger,
)

# Log security event for API key status (without exposing the key)
if SecurityManager:
    SecurityManager.log_security_event(
        logger,
        "api_key_initialization",
        {
            "has_api_key": API_KEY is not None,
            "secret_configured": bool(SECRET_NAME),
            "function_name": "search_semantic_scholar",
        },
    )


def rate_limit_and_retry(max_retries: int = 3, base_delay: float = 1.0):
    """
    Decorator to add rate limiting and retry logic to API calls.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries (exponential backoff)
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    # Add rate limiting delay (except for first attempt)
                    if attempt > 0:
                        delay = base_delay * (2 ** (attempt - 1))  # Exponential backoff
                        logger.info(
                            f"Retrying after {delay:.1f}s delay (attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(delay)

                    return func(*args, **kwargs)

                except RequestException as e:
                    last_exception = e

                    # Don't retry on client errors (4xx)
                    if hasattr(e, "response") and e.response is not None:
                        status_code = e.response.status_code
                        if 400 <= status_code < 500:
                            logger.error(f"Client error {status_code}, not retrying")
                            raise e

                    # Log retry attempt for server errors and network issues
                    if attempt < max_retries:
                        logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
                    else:
                        logger.error(
                            f"Request failed after {max_retries + 1} attempts: {e}"
                        )

            # If we get here, all retries failed
            raise last_exception

        return wrapper

    return decorator


@rate_limit_and_retry(max_retries=3, base_delay=1.0)
def _make_request(url: str, params: dict, api_key: str = None):
    """
    Generic request helper for Semantic Scholar API with rate limiting and retry logic.

    Args:
        url: API endpoint URL
        params: Query parameters
        api_key: Optional API key for authentication

    Returns:
        JSON response from API

    Raises:
        RequestException: If request fails after retries
    """
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    logger.debug(f"Making request to {url} with params: {params}")
    resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@PerformanceMonitor.monitor_operation("semantic_scholar_search", log_parameters=False)
def search_paper(query: str, limit: int, fields: str, api_key: str = None):
    """Performs a keyword-based search for papers."""
    url = f"{SEMANTIC_SCHOLAR_BASE}/paper/search"
    params = {"query": query, "limit": limit, "fields": fields}
    return _make_request(url, params, api_key).get("data", [])


def validate_action_parameters(action: str, body: Dict[str, Any]) -> None:
    """
    Validate action-specific parameters.

    Args:
        action: The action to validate
        body: Request body containing parameters

    Raises:
        ValueError: If required parameters are missing or invalid
    """
    valid_actions = ["search_paper", "get_paper", "get_references", "get_citations"]

    if action not in valid_actions:
        raise ValueError(
            f"Invalid action '{action}'. Valid actions: {', '.join(valid_actions)}"
        )

    if action == "search_paper":
        if not body.get("query"):
            raise ValueError("Query parameter is required for search_paper action")
        if not isinstance(body.get("query"), str):
            raise ValueError("Query parameter must be a string")

        # Validate optional limit parameter
        limit = body.get("limit")
        if limit is not None:
            try:
                limit = int(limit)
                if limit <= 0 or limit > 100:
                    raise ValueError("Limit must be between 1 and 100")
            except (ValueError, TypeError):
                raise ValueError("Limit parameter must be a valid integer")

    elif action in ["get_paper", "get_references", "get_citations"]:
        if not body.get("paper_id"):
            raise ValueError(f"paper_id parameter is required for {action} action")
        if not isinstance(body.get("paper_id"), str):
            raise ValueError("paper_id parameter must be a string")


@StandardErrorHandler.handle_common_exceptions
def lambda_handler(event, context):
    """
    Lambda handler for Semantic Scholar search operations.
    """
    logger.info(f"Processing Semantic Scholar request")

    # Parse request body
    body = RequestParser.parse_event_body(event)

    # Validate required fields
    RequestParser.validate_required_fields(body, ["action"])

    action = body["action"]

    # Validate action-specific parameters
    validate_action_parameters(action, body)

    results = None

    try:
        if action == "search_paper":
            query = body["query"]
            limit = body.get("limit", SEARCH_LIMIT)
            fields = body.get("fields", "title,authors,abstract,url")

            logger.info(f"Searching papers for query: '{query}' with limit: {limit}")
            papers = search_paper(query, limit, fields, api_key=API_KEY)

            # Format results consistently
            results = []
            for p in papers:
                results.append(
                    {
                        "title": p.get("title"),
                        "authors": [
                            author.get("name") for author in p.get("authors", [])
                        ],
                        "abstract": p.get("abstract"),
                        "url": p.get("url"),
                    }
                )

            logger.info(f"Found {len(results)} papers")

        return ResponseFormatter.create_success_response(results)

    except Timeout:
        LambdaLogger.log_structured_error(
            logger,
            TimeoutError("Semantic Scholar API timeout"),
            "semantic_scholar_request",
            "timeout",
            action=action,
            api_key_available=API_KEY is not None,
        )
        return ResponseFormatter.create_error_response(
            504, "Gateway Timeout", "Request to Semantic Scholar API timed out"
        )
    except RequestException as e:
        # Check if it's a client error (4xx) or server error (5xx)
        if hasattr(e, "response") and e.response is not None:
            status_code = e.response.status_code
            LambdaLogger.log_structured_error(
                logger,
                e,
                "semantic_scholar_request",
                "http_error",
                action=action,
                status_code=status_code,
                api_key_available=API_KEY is not None,
            )
            if 400 <= status_code < 500:
                return ResponseFormatter.create_error_response(
                    400,
                    "Client Error",
                    f"Semantic Scholar API client error: {status_code}",
                )
            else:
                return ResponseFormatter.create_error_response(
                    502,
                    "Bad Gateway",
                    f"Semantic Scholar API server error: {status_code}",
                )
        else:
            LambdaLogger.log_structured_error(
                logger,
                e,
                "semantic_scholar_request",
                "connection_error",
                action=action,
                api_key_available=API_KEY is not None,
            )
            return ResponseFormatter.create_error_response(
                502, "Bad Gateway", "Failed to connect to Semantic Scholar API"
            )
