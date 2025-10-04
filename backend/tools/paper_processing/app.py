import json
import sys
import os
import boto3
from typing import Dict, Any

# Add the shared utilities to the path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "shared"))

# Import shared utilities
from shared.lambda_utils import (
    setup_lambda_environment,
    RequestParser,
    ResponseFormatter,
    StandardErrorHandler,
    LambdaLogger,
)

# Environment configuration
REQUIRED_ENV_VARS = ["STATE_MACHINE_ARN"]
OPTIONAL_ENV_VARS = {
    "LOG_LEVEL": "INFO",
}

# Setup environment (done outside handler for reuse)
config, logger = setup_lambda_environment(
    required_env_vars=REQUIRED_ENV_VARS,
    optional_env_vars=OPTIONAL_ENV_VARS,
    log_level=OPTIONAL_ENV_VARS["LOG_LEVEL"],
)

# Initialize Step Functions client
sfn_client = boto3.client("stepfunctions")


def start_state_machine_execution(pdf_url: str) -> Dict[str, Any]:
    """
    Starts the execution of the Step Functions state machine with pdf_url in input.
    Args:
        pdf_url: URL of the PDF to process
    Returns:
        Dictionary with execution ARN and start timestamp
    Raises:
        Exception if execution start fails
    """
    state_machine_arn = config["STATE_MACHINE_ARN"]
    input_payload = json.dumps({"pdf_url": pdf_url})

    response = sfn_client.start_execution(
        stateMachineArn=state_machine_arn,
        input=input_payload,
    )
    return {
        "executionArn": response["executionArn"],
        "startDate": response["startDate"].isoformat(),
    }


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda handler to start Step Functions execution with pdf_url from request body.
    Args:
        event: Lambda event dictionary
        context: Lambda context object
    Returns:
        Standardized Lambda response dictionary
    """
    logger.info("Received request to start Step Functions execution")

    # Parse and validate request body
    body = RequestParser.parse_event_body(event)
    RequestParser.validate_required_fields(body, ["pdf_url"])

    pdf_url = body["pdf_url"]

    if not pdf_url or not isinstance(pdf_url, str) or not pdf_url.strip():
        raise ValueError("pdf_url must be a non-empty string")

    logger.info(f"Starting state machine execution with pdf_url: {pdf_url}")

    try:
        exec_response = start_state_machine_execution(pdf_url)

        LambdaLogger.log_performance_metrics(
            logger,
            "start_state_machine_execution_complete",
            0,
            True,
            pdf_url_length=len(pdf_url),
            executionArn=exec_response.get("executionArn"),
        )

        return ResponseFormatter.create_success_response(
            {
                "message": "Step Functions execution started successfully",
                "execution": exec_response,
            }
        )
    except Exception as e:
        logger.error(f"Failed to start state machine execution: {e}")
        return ResponseFormatter.create_error_response(
            500,
            "Execution Error",
            "Failed to start Step Functions execution",
            str(e),
        )
