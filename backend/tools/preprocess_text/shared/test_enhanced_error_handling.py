#!/usr/bin/env python3
"""
Test script to verify enhanced error handling and monitoring capabilities.
"""

import json
import sys
import os
import time
from unittest.mock import Mock, patch

# Add the shared utilities to the path
sys.path.append(os.path.dirname(__file__))

from lambda_utils import (
    StandardErrorHandler,
    LambdaLogger,
    PerformanceMonitor,
    ResponseFormatter,
)


def test_error_categorization():
    """Test HTTP error categorization."""
    print("Testing error categorization...")

    # Test client errors
    status_code, error_type, category = StandardErrorHandler.categorize_http_error(400)
    assert status_code == 400 and category == "client_error"
    print("✓ 400 Bad Request categorized correctly")

    status_code, error_type, category = StandardErrorHandler.categorize_http_error(404)
    assert status_code == 404 and category == "client_error"
    print("✓ 404 Not Found categorized correctly")

    status_code, error_type, category = StandardErrorHandler.categorize_http_error(429)
    assert status_code == 429 and category == "client_error"
    print("✓ 429 Too Many Requests categorized correctly")

    # Test server errors
    status_code, error_type, category = StandardErrorHandler.categorize_http_error(500)
    assert status_code == 502 and category == "server_error"
    print("✓ 500 Server Error mapped to 502 Bad Gateway")

    status_code, error_type, category = StandardErrorHandler.categorize_http_error(503)
    assert status_code == 502 and category == "server_error"
    print("✓ 503 Service Unavailable mapped to 502 Bad Gateway")


def test_timeout_handling():
    """Test network timeout handling."""
    print("\nTesting timeout handling...")

    response = StandardErrorHandler.handle_network_timeout()
    assert response["statusCode"] == 504

    body = json.loads(response["body"])
    assert body["error"] == "Gateway Timeout"
    print("✓ Network timeout returns 504 Gateway Timeout")


def test_structured_logging():
    """Test structured logging capabilities."""
    print("\nTesting structured logging...")

    # Mock logger
    mock_logger = Mock()

    # Test performance metrics logging
    LambdaLogger.log_performance_metrics(
        mock_logger, "test_operation", 150.5, True, result_count=10, data_size=1024
    )

    # Verify the logger was called
    assert mock_logger.info.called
    call_args = mock_logger.info.call_args[0][0]
    assert "PERFORMANCE_METRICS:" in call_args
    assert "test_operation" in call_args
    print("✓ Performance metrics logged correctly")

    # Test structured error logging
    test_error = ValueError("Test validation error")
    LambdaLogger.log_structured_error(
        mock_logger,
        test_error,
        "test_operation",
        "validation",
        user_id="test_user",
        request_id="req_123",
    )

    # Verify error logging
    assert mock_logger.error.called
    error_call_args = mock_logger.error.call_args[0][0]
    assert "STRUCTURED_ERROR:" in error_call_args
    assert "validation" in error_call_args
    print("✓ Structured error logging works correctly")


def test_performance_monitor():
    """Test performance monitoring decorator."""
    print("\nTesting performance monitoring...")

    @PerformanceMonitor.monitor_operation("test_function")
    def sample_function(delay=0.1):
        time.sleep(delay)
        return {"result": "success", "items": [1, 2, 3]}

    # Mock logger to capture logs
    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        result = sample_function(0.05)

        # Verify function executed correctly
        assert result["result"] == "success"

        # Verify logging was called (start, metrics, end)
        assert mock_logger.info.call_count >= 2  # At least start and end
        print("✓ Performance monitoring decorator works correctly")


def test_aws_error_handling():
    """Test AWS error handling."""
    print("\nTesting AWS error handling...")

    # Mock ClientError
    from botocore.exceptions import ClientError

    # Test access denied error
    error_response = {
        "Error": {"Code": "AccessDenied", "Message": "Access denied to resource"}
    }

    client_error = ClientError(error_response, "GetObject")
    response = StandardErrorHandler.handle_aws_error(client_error)

    assert response["statusCode"] == 403
    body = json.loads(response["body"])
    assert body["error"] == "Access Denied"
    print("✓ AWS AccessDenied error handled correctly")

    # Test resource not found error
    error_response = {
        "Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist"}
    }

    client_error = ClientError(error_response, "GetObject")
    response = StandardErrorHandler.handle_aws_error(client_error)

    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert body["error"] == "Resource Not Found"
    print("✓ AWS NoSuchKey error handled correctly")


def main():
    """Run all tests."""
    print("Testing Enhanced Error Handling and Monitoring")
    print("=" * 50)

    try:
        test_error_categorization()
        test_timeout_handling()
        test_structured_logging()
        test_performance_monitor()
        test_aws_error_handling()

        print("\n" + "=" * 50)
        print("✅ All tests passed! Enhanced error handling is working correctly.")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
