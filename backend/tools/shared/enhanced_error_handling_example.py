#!/usr/bin/env python3
"""
Example demonstrating enhanced error handling and monitoring capabilities.

This example shows how to use the new error categorization, structured logging,
and performance monitoring features in Lambda functions.
"""

import json
import time
import logging
from typing import Dict, Any

# Import enhanced utilities
from lambda_utils import (
    setup_lambda_environment,
    RequestParser,
    ResponseFormatter,
    StandardErrorHandler,
    PerformanceMonitor,
    LambdaLogger,
)


# Example 1: Using performance monitoring decorator
@PerformanceMonitor.monitor_operation("data_processing", log_parameters=False)
def process_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Example function with performance monitoring.

    The decorator automatically logs:
    - Operation start with correlation ID
    - Performance metrics (duration, success/failure)
    - Operation end with results summary
    """
    # Simulate some processing time
    time.sleep(0.1)

    # Process the data
    processed_items = []
    for item in data.get("items", []):
        processed_items.append({"id": item, "processed": True})

    return {
        "processed_count": len(processed_items),
        "items": processed_items,
        "status": "completed",
    }


# Example 2: Lambda handler with comprehensive error handling
@StandardErrorHandler.handle_common_exceptions
def example_lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Example Lambda handler demonstrating enhanced error handling.

    The decorator automatically handles:
    - ValueError -> 400 Bad Request
    - requests.Timeout -> 504 Gateway Timeout
    - requests.HTTPError -> Appropriate 4xx/5xx based on status code
    - requests.ConnectionError -> 502 Bad Gateway
    - ClientError -> Appropriate response based on AWS error code
    - Exception -> 500 Internal Server Error

    All errors are logged with structured logging for better observability.
    """
    # Setup environment (this would normally be done outside the handler)
    config, logger = setup_lambda_environment(
        required_env_vars=[],
        optional_env_vars={"PROCESSING_TIMEOUT": "30", "MAX_ITEMS": "100"},
        log_level="INFO",
    )

    logger.info("Processing example request")

    # Parse and validate request
    body = RequestParser.parse_event_body(event)
    RequestParser.validate_required_fields(body, ["action"])

    action = body["action"]

    # Log operation start with structured logging
    operation_id = LambdaLogger.log_operation_start(
        logger,
        "example_operation",
        action=action,
        event_source=event.get("source", "unknown"),
    )

    start_time = time.time()

    try:
        if action == "process_data":
            # Validate data parameter
            if "data" not in body:
                raise ValueError("Missing 'data' parameter for process_data action")

            # Process data with monitoring
            result = process_data(body["data"])

            # Log success metrics
            duration_ms = (time.time() - start_time) * 1000
            LambdaLogger.log_performance_metrics(
                logger,
                "example_operation_complete",
                duration_ms,
                True,
                action=action,
                items_processed=result["processed_count"],
            )

            return ResponseFormatter.create_success_response(result)

        elif action == "simulate_error":
            # Demonstrate different error types
            error_type = body.get("error_type", "validation")

            if error_type == "validation":
                raise ValueError("Simulated validation error for testing")
            elif error_type == "timeout":
                import requests

                raise requests.exceptions.Timeout("Simulated timeout error")
            elif error_type == "http_404":
                import requests

                response = type("MockResponse", (), {"status_code": 404})()
                raise requests.exceptions.HTTPError("Not found", response=response)
            elif error_type == "aws_access":
                from botocore.exceptions import ClientError

                error_response = {
                    "Error": {"Code": "AccessDenied", "Message": "Access denied"}
                }
                raise ClientError(error_response, "GetObject")
            else:
                raise Exception("Simulated unexpected error")

        else:
            raise ValueError(f"Unknown action: {action}")

    except Exception as e:
        # Log structured error (this is also done by the decorator, but shown for example)
        duration_ms = (time.time() - start_time) * 1000
        LambdaLogger.log_structured_error(
            logger,
            e,
            "example_operation",
            "operation_failed",
            action=action,
            operation_id=operation_id,
            duration_ms=duration_ms,
        )

        # Re-raise to let the decorator handle the response
        raise


# Example 3: Manual error handling for specific cases
def example_with_manual_error_handling(
    event: Dict[str, Any], context
) -> Dict[str, Any]:
    """
    Example showing manual error handling for specific business logic.
    """
    config, logger = setup_lambda_environment()

    try:
        # Some operation that might fail
        result = risky_operation()
        return ResponseFormatter.create_success_response(result)

    except ValueError as e:
        # Handle validation errors specifically
        LambdaLogger.log_structured_error(
            logger, e, "risky_operation", "validation", input_data=event.get("body", {})
        )
        return ResponseFormatter.create_error_response(400, "Validation Error", str(e))

    except Exception as e:
        # Handle unexpected errors
        LambdaLogger.log_structured_error(
            logger,
            e,
            "risky_operation",
            "unexpected",
            function_name="example_with_manual_error_handling",
        )
        return ResponseFormatter.create_error_response(
            500, "Internal Server Error", "An unexpected error occurred"
        )


def risky_operation():
    """Simulate a risky operation that might fail."""
    import random

    if random.random() < 0.3:  # 30% chance of failure
        raise ValueError("Random validation failure for demonstration")
    return {"status": "success", "data": "processed"}


# Example 4: Demonstrating error categorization
def demonstrate_error_categorization():
    """Show how different HTTP errors are categorized."""

    print("HTTP Error Categorization Examples:")
    print("-" * 40)

    test_cases = [
        (400, "Bad Request"),
        (401, "Unauthorized"),
        (403, "Forbidden"),
        (404, "Not Found"),
        (429, "Too Many Requests"),
        (500, "Internal Server Error"),
        (502, "Bad Gateway"),
        (503, "Service Unavailable"),
    ]

    for status_code, description in test_cases:
        lambda_code, error_type, category = StandardErrorHandler.categorize_http_error(
            status_code
        )
        print(f"{status_code} {description} -> {lambda_code} {error_type} ({category})")


if __name__ == "__main__":
    # Demonstrate error categorization
    demonstrate_error_categorization()

    print("\n" + "=" * 50)
    print("Enhanced Error Handling Example")
    print("=" * 50)

    # Test successful operation
    print("\n1. Testing successful operation:")
    test_event = {
        "body": json.dumps(
            {"action": "process_data", "data": {"items": ["item1", "item2", "item3"]}}
        )
    }

    try:
        result = example_lambda_handler(test_event, None)
        print(
            f"✓ Success: {json.loads(result['body'])['processed_count']} items processed"
        )
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test validation error
    print("\n2. Testing validation error:")
    test_event = {
        "body": json.dumps({"action": "simulate_error", "error_type": "validation"})
    }

    try:
        result = example_lambda_handler(test_event, None)
        print(f"Unexpected success: {result}")
    except Exception as e:
        print(f"✓ Validation error handled: {type(e).__name__}")

    print("\n✅ Example completed successfully!")
