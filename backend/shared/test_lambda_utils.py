"""
Basic tests for shared Lambda utilities.
These tests verify the core functionality of the shared utilities.
"""

import json
import os
import logging
from unittest.mock import patch, MagicMock

import sys
import os

sys.path.append(os.path.dirname(__file__))

from lambda_utils import (
    LambdaLogger,
    EnvironmentValidator,
    RequestParser,
    ResponseFormatter,
    AWSClientManager,
    StandardErrorHandler,
    setup_lambda_environment,
)


def test_lambda_logger():
    """Test logging setup functionality."""
    logger = LambdaLogger.setup_logger("test-logger", "DEBUG")
    assert logger.name == "test-logger"
    assert logger.level == logging.DEBUG
    print("✓ LambdaLogger test passed")


def test_environment_validator():
    """Test environment variable validation."""
    # Test required variables
    with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
        config = EnvironmentValidator.validate_required_vars(["TEST_VAR"])
        assert config["TEST_VAR"] == "test_value"

    # Test optional variables
    optional_config = EnvironmentValidator.get_optional_vars(
        {"MISSING_VAR": "default_value", "EXISTING_VAR": "default"}
    )
    assert optional_config["MISSING_VAR"] == "default_value"

    print("✓ EnvironmentValidator test passed")


def test_request_parser():
    """Test request parsing functionality."""
    # Test JSON string body
    event = {"body": '{"query": "test", "limit": 5}'}
    body = RequestParser.parse_event_body(event)
    assert body["query"] == "test"
    assert body["limit"] == 5

    # Test dict body
    event = {"body": {"query": "test"}}
    body = RequestParser.parse_event_body(event)
    assert body["query"] == "test"

    # Test field validation
    try:
        RequestParser.validate_required_fields({"query": "test"}, ["query", "missing"])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "missing" in str(e)

    print("✓ RequestParser test passed")


def test_response_formatter():
    """Test response formatting functionality."""
    # Test success response
    response = ResponseFormatter.create_success_response({"result": "test"})
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["result"] == "test"

    # Test error response
    error_response = ResponseFormatter.create_error_response(
        400, "Test Error", "Test message", "Test details"
    )
    assert error_response["statusCode"] == 400
    error_body = json.loads(error_response["body"])
    assert error_body["error"] == "Test Error"
    assert error_body["message"] == "Test message"
    assert error_body["details"] == "Test details"
    assert "timestamp" in error_body

    print("✓ ResponseFormatter test passed")


def test_aws_client_manager():
    """Test AWS client management."""
    with patch("boto3.client") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.return_value = mock_client

        # Test client creation and reuse
        client1 = AWSClientManager.get_client("s3")
        client2 = AWSClientManager.get_client("s3")

        assert client1 is client2  # Should be the same instance
        mock_boto3.assert_called_once_with("s3")

    print("✓ AWSClientManager test passed")


def test_error_handler_decorator():
    """Test the error handling decorator."""

    @StandardErrorHandler.handle_common_exceptions
    def test_function(event, context):
        if event.get("error_type") == "value_error":
            raise ValueError("Test validation error")
        elif event.get("error_type") == "general_error":
            raise Exception("Test general error")
        else:
            return ResponseFormatter.create_success_response({"success": True})

    # Test successful execution
    response = test_function({}, None)
    assert response["statusCode"] == 200

    # Test ValueError handling
    response = test_function({"error_type": "value_error"}, None)
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert body["error"] == "Validation Error"

    # Test general exception handling
    response = test_function({"error_type": "general_error"}, None)
    assert response["statusCode"] == 500
    body = json.loads(response["body"])
    assert body["error"] == "Internal Server Error"

    print("✓ StandardErrorHandler test passed")


def test_setup_lambda_environment():
    """Test complete environment setup."""
    with patch.dict(os.environ, {"REQUIRED_VAR": "test_value"}):
        config, logger = setup_lambda_environment(
            required_env_vars=["REQUIRED_VAR"],
            optional_env_vars={"OPTIONAL_VAR": "default"},
            log_level="DEBUG",
        )

        assert config["REQUIRED_VAR"] == "test_value"
        assert config["OPTIONAL_VAR"] == "default"
        assert logger.level == logging.DEBUG

    print("✓ setup_lambda_environment test passed")


def run_all_tests():
    """Run all tests."""
    print("Running shared Lambda utilities tests...")

    test_lambda_logger()
    test_environment_validator()
    test_request_parser()
    test_response_formatter()
    test_aws_client_manager()
    test_error_handler_decorator()
    test_setup_lambda_environment()

    print("\n✅ All tests passed!")


if __name__ == "__main__":
    run_all_tests()
