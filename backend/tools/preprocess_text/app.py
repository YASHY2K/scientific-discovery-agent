import os
import json
import logging
import boto3
import re
from datetime import datetime
from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import Dict, Any, List

# Import shared utilities
import sys

sys.path.append("/opt")
from shared.lambda_utils import (
    setup_lambda_environment,
    RequestParser,
    ResponseFormatter,
    AWSClientManager,
    StandardErrorHandler,
    PerformanceMonitor,
    LambdaLogger,
)

# Initialize AWS clients using shared utilities
s3_client = AWSClientManager.get_client("s3")

# Environment variable configuration
REQUIRED_ENV_VARS = ["PROCESSED_BUCKET_NAME"]
OPTIONAL_ENV_VARS = {
    "CHUNK_SIZE": "1000",
    "CHUNK_OVERLAP": "200",
    "MIN_CHUNK_SIZE": "100",
    "MAX_CHUNK_SIZE": "4000",
    "MIN_TEXT_LENGTH": "50",
    "SEPARATORS": "\n\n,\n,. , ,",
    "LOG_LEVEL": "INFO",
}

# Setup environment and logging
config, logger = setup_lambda_environment(
    required_env_vars=REQUIRED_ENV_VARS,
    optional_env_vars=OPTIONAL_ENV_VARS,
    log_level="INFO",
)


def validate_text_quality(text: str, min_length: int = 50) -> bool:
    """
    Validate text quality before processing.

    Args:
        text: Input text to validate
        min_length: Minimum acceptable text length

    Returns:
        True if text meets quality standards, False otherwise
    """
    if not text or not isinstance(text, str):
        return False

    # Check minimum length
    if len(text.strip()) < min_length:
        return False

    # Check for reasonable character distribution (not just whitespace/special chars)
    alphanumeric_chars = sum(1 for c in text if c.isalnum())
    if alphanumeric_chars < min_length * 0.3:  # At least 30% alphanumeric
        return False

    return True


@PerformanceMonitor.monitor_operation("text_cleaning", log_parameters=False)
def clean_text(text: str) -> str:
    """
    Enhanced text cleaning with improved algorithms for better quality.
    Removes common PDF extraction artifacts and normalizes whitespace.
    """
    if not text:
        return ""

    # Remove page numbers and headers/footers
    text = re.sub(r"^\s*Page \d+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)  # Standalone numbers

    # Remove common PDF artifacts
    text = re.sub(
        r"^\s*[A-Z\s]{10,}\s*$", "", text, flags=re.MULTILINE
    )  # ALL CAPS headers
    text = re.sub(r"^\s*\.{3,}\s*$", "", text, flags=re.MULTILINE)  # Dot leaders
    text = re.sub(r"^\s*[-_=]{3,}\s*$", "", text, flags=re.MULTILINE)  # Separator lines

    # Fix common OCR/extraction issues
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)  # Add space between camelCase
    text = re.sub(r"([.!?])([A-Z])", r"\1 \2", text)  # Add space after sentence endings

    # Normalize whitespace: replace multiple spaces/newlines with appropriate spacing
    text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)  # Max 2 consecutive newlines
    text = re.sub(r"[ \t]+", " ", text)  # Multiple spaces to single space
    text = re.sub(r"\n ", "\n", text)  # Remove spaces at start of lines

    # Remove characters that are often a result of decoding errors
    text = text.replace("\ufffd", "")
    text = text.replace("\x00", "")

    return text.strip()


def get_chunking_config(config: Dict[str, str]) -> Dict[str, Any]:
    """
    Parse and validate chunking configuration from environment variables.

    Args:
        config: Environment configuration dictionary

    Returns:
        Validated chunking configuration

    Raises:
        ValueError: If configuration values are invalid
    """
    try:
        chunk_size = int(config["CHUNK_SIZE"])
        chunk_overlap = int(config["CHUNK_OVERLAP"])
        min_chunk_size = int(config["MIN_CHUNK_SIZE"])
        max_chunk_size = int(config["MAX_CHUNK_SIZE"])
        min_text_length = int(config["MIN_TEXT_LENGTH"])

        # Validate ranges
        if chunk_size < min_chunk_size or chunk_size > max_chunk_size:
            raise ValueError(
                f"CHUNK_SIZE must be between {min_chunk_size} and {max_chunk_size}"
            )

        if chunk_overlap >= chunk_size:
            raise ValueError("CHUNK_OVERLAP must be less than CHUNK_SIZE")

        if chunk_overlap < 0:
            raise ValueError("CHUNK_OVERLAP must be non-negative")

        # Parse separators
        separators = [s.strip() for s in config["SEPARATORS"].split(",")]

        return {
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "min_chunk_size": min_chunk_size,
            "max_chunk_size": max_chunk_size,
            "min_text_length": min_text_length,
            "separators": separators,
        }

    except (ValueError, KeyError) as e:
        raise ValueError(f"Invalid chunking configuration: {e}")


@StandardErrorHandler.handle_common_exceptions
def lambda_handler(event, context):
    """
    Handles the text preprocessing stage: downloads extracted text from S3,
    cleans it, splits it into semantic chunks, and uploads the chunks back to S3.
    """
    logger.info(f"Received event: {json.dumps(event, default=str)}")

    # Parse request body
    body = RequestParser.parse_event_body(event)

    # Handle both direct body format and artifacts format for backward compatibility
    if "artifacts" in event:
        artifacts = event["artifacts"]
        full_text_s3_path = artifacts.get("full_text_s3_path")
    else:
        full_text_s3_path = body.get("full_text_s3_path")

    if not full_text_s3_path:
        raise ValueError("'full_text_s3_path' not found in request")

    # Get chunking configuration
    chunking_config = get_chunking_config(config)
    logger.info(f"Using chunking configuration: {chunking_config}")

    # Parse S3 path
    if not full_text_s3_path.startswith("s3://"):
        raise ValueError("Invalid S3 path format. Must start with 's3://'")

    s3_parts = full_text_s3_path.replace("s3://", "").split("/", 1)
    if len(s3_parts) != 2:
        raise ValueError("Invalid S3 path format. Must be 's3://bucket/key'")

    bucket, key = s3_parts
    base_path = os.path.dirname(key)

    # Download the full text
    logger.info(f"Downloading text from s3://{bucket}/{key}")
    try:
        text_object = s3_client.get_object(Bucket=bucket, Key=key)
        raw_text = text_object["Body"].read().decode("utf-8")
    except Exception as e:
        raise ValueError(f"Failed to download text from S3: {e}")

    # Validate text quality
    if not validate_text_quality(raw_text, chunking_config["min_text_length"]):
        raise ValueError(
            f"Text quality validation failed. Text must be at least "
            f"{chunking_config['min_text_length']} characters with reasonable content."
        )

    # Clean the text
    logger.info("Cleaning extracted text")
    cleaned_text = clean_text(raw_text)

    # Validate cleaned text
    if not validate_text_quality(cleaned_text, chunking_config["min_text_length"]):
        raise ValueError("Text quality validation failed after cleaning")

    # Initialize the recursive text splitter with configurable parameters
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunking_config["chunk_size"],
        chunk_overlap=chunking_config["chunk_overlap"],
        separators=chunking_config["separators"],
    )

    # Create chunks
    logger.info(
        f"Chunking text into pieces of ~{chunking_config['chunk_size']} characters"
    )
    chunks = text_splitter.split_text(cleaned_text)

    # Filter out chunks that are too small
    filtered_chunks = [
        chunk
        for chunk in chunks
        if len(chunk.strip()) >= chunking_config["min_chunk_size"]
    ]

    if not filtered_chunks:
        raise ValueError("No valid chunks created after filtering")

    logger.info(f"Created {len(filtered_chunks)} chunks (filtered from {len(chunks)})")

    # Store chunks in a structured JSON object with enhanced metadata
    chunks_data = {
        "parent_document": full_text_s3_path,
        "processing_metadata": {
            "chunking_strategy": "RecursiveCharacterTextSplitter",
            "chunk_size": chunking_config["chunk_size"],
            "chunk_overlap": chunking_config["chunk_overlap"],
            "separators": chunking_config["separators"],
            "min_chunk_size": chunking_config["min_chunk_size"],
            "original_text_length": len(raw_text),
            "cleaned_text_length": len(cleaned_text),
            "total_chunks_created": len(chunks),
            "chunks_after_filtering": len(filtered_chunks),
            "processing_timestamp": json.dumps(
                datetime.utcnow().isoformat() + "Z"
            ).strip('"'),
        },
        "chunk_count": len(filtered_chunks),
        "chunks": filtered_chunks,
    }

    chunks_key = f"{base_path}/chunks.json"
    logger.info(
        f"Uploading {len(filtered_chunks)} chunks to s3://{config['PROCESSED_BUCKET_NAME']}/{chunks_key}"
    )

    try:
        s3_client.put_object(
            Bucket=config["PROCESSED_BUCKET_NAME"],
            Key=chunks_key,
            Body=json.dumps(chunks_data, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
    except Exception as e:
        raise ValueError(f"Failed to upload chunks to S3: {e}")

    # Prepare response data
    result_data = {
        "chunks_s3_path": f"s3://{config['PROCESSED_BUCKET_NAME']}/{chunks_key}",
        "processing_summary": {
            "chunks_created": len(filtered_chunks),
            "original_text_length": len(raw_text),
            "cleaned_text_length": len(cleaned_text),
            "chunking_config": chunking_config,
        },
    }

    # Handle both response formats for backward compatibility
    if "artifacts" in event:
        event["artifacts"]["chunks_s3_path"] = result_data["chunks_s3_path"]
        return ResponseFormatter.create_success_response(event)
    else:
        return ResponseFormatter.create_success_response(result_data)
