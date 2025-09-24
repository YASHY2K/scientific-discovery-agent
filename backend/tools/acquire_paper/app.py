import os
import json
import logging
import boto3
import requests
from urllib.parse import urlparse
import re
import time
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError

# Import shared utilities
from shared.lambda_utils import (
    setup_lambda_environment,
    RequestParser,
    ResponseFormatter,
    AWSClientManager,
    StandardErrorHandler,
    PerformanceMonitor,
    LambdaLogger,
)

# Environment configuration
REQUIRED_ENV_VARS = ["RAW_BUCKET_NAME"]
OPTIONAL_ENV_VARS = {
    "HTTP_TIMEOUT_SECONDS": "60",
    "SECRET_NAME": "",
    "SEMANTIC_SCHOLAR_API_KEY": "",
}

# Initialize environment and logging
config, logger = setup_lambda_environment(
    required_env_vars=REQUIRED_ENV_VARS,
    optional_env_vars=OPTIONAL_ENV_VARS,
    log_level="INFO",
)

# Initialize AWS clients (reused across invocations)
s3_client = AWSClientManager.get_client("s3")

# Get API key from Secrets Manager or environment
API_KEY = None
if config.get("SECRET_NAME"):
    try:
        secret_data = AWSClientManager.get_secret(config["SECRET_NAME"])
        API_KEY = secret_data.get("SEMANTIC_SCHOLAR_API_KEY")
        if API_KEY:
            logger.info(
                "Successfully loaded Semantic Scholar API key from Secrets Manager"
            )
        else:
            logger.warning("SEMANTIC_SCHOLAR_API_KEY not found in secret")
    except Exception as e:
        logger.error(f"Failed to retrieve API key from Secrets Manager: {e}")
elif config.get("SEMANTIC_SCHOLAR_API_KEY"):
    API_KEY = config["SEMANTIC_SCHOLAR_API_KEY"]
    logger.info("Loaded Semantic Scholar API key from environment")
else:
    logger.warning("No Semantic Scholar API key configured")


def validate_url(url: str) -> bool:
    """
    Validate that the URL is properly formatted and uses allowed schemes.

    Args:
        url: URL to validate

    Returns:
        True if URL is valid, False otherwise
    """
    try:
        parsed = urlparse(url)
        # Check for valid scheme and netloc
        if not parsed.scheme or not parsed.netloc:
            return False
        # Only allow HTTP and HTTPS
        if parsed.scheme not in ["http", "https"]:
            return False
        # Basic domain validation
        if not re.match(r"^[a-zA-Z0-9.-]+$", parsed.netloc.split(":")[0]):
            return False
        return True
    except Exception:
        return False


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and ensure valid S3 key.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename safe for S3
    """
    # Remove path components and keep only the basename
    filename = os.path.basename(filename)
    # Remove or replace invalid characters
    filename = re.sub(r"[^\w\-_\.]", "_", filename)
    # Ensure it ends with .pdf
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    # Limit length
    if len(filename) > 100:
        name_part = filename[:-4][:96]  # Keep extension
        filename = name_part + ".pdf"
    return filename


def validate_s3_path(s3_path: str) -> tuple[str, str]:
    """
    Validate and parse S3 path into bucket and key components.

    Args:
        s3_path: S3 path in format s3://bucket/key

    Returns:
        Tuple of (bucket_name, key)

    Raises:
        ValueError: If S3 path is invalid
    """
    if not s3_path.startswith("s3://"):
        raise ValueError(f"Invalid S3 path format: {s3_path}")

    path_parts = s3_path[5:].split("/", 1)
    if len(path_parts) != 2 or not path_parts[0] or not path_parts[1]:
        raise ValueError(f"Invalid S3 path format: {s3_path}")

    bucket_name, key = path_parts

    # Validate bucket name format (basic validation)
    if (
        not re.match(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$", bucket_name)
        and len(bucket_name) > 2
    ):
        if not re.match(r"^[a-z0-9]$", bucket_name):  # Single character bucket names
            raise ValueError(f"Invalid S3 bucket name: {bucket_name}")

    return bucket_name, key


@PerformanceMonitor.monitor_operation("download_paper", log_parameters=False)
def download_with_retry(
    url: str, max_retries: int = 3, backoff_factor: float = 1.0
) -> requests.Response:
    """
    Download file with exponential backoff retry logic.

    Args:
        url: URL to download from
        max_retries: Maximum number of retry attempts
        backoff_factor: Backoff multiplier for retry delays

    Returns:
        Response object with streaming content

    Raises:
        requests.RequestException: If all retry attempts fail
    """
    timeout = float(config["HTTP_TIMEOUT_SECONDS"])

    for attempt in range(max_retries + 1):
        try:
            logger.info(f"Download attempt {attempt + 1} for URL: {url}")
            response = requests.get(url, timeout=timeout, stream=True)
            response.raise_for_status()
            return response

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt < max_retries:
                delay = backoff_factor * (2**attempt)
                logger.warning(
                    f"Download attempt {attempt + 1} failed: {e}. Retrying in {delay}s..."
                )
                time.sleep(delay)
            else:
                logger.error(f"All {max_retries + 1} download attempts failed")
                raise

        except requests.exceptions.HTTPError as e:
            # Don't retry on client errors (4xx)
            if e.response and 400 <= e.response.status_code < 500:
                logger.error(
                    f"Client error {e.response.status_code}, not retrying: {e}"
                )
                raise
            # Retry on server errors (5xx)
            elif attempt < max_retries:
                delay = backoff_factor * (2**attempt)
                logger.warning(
                    f"Server error on attempt {attempt + 1}: {e}. Retrying in {delay}s..."
                )
                time.sleep(delay)
            else:
                logger.error(f"All {max_retries + 1} download attempts failed")
                raise

        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                delay = backoff_factor * (2**attempt)
                logger.warning(
                    f"Request error on attempt {attempt + 1}: {e}. Retrying in {delay}s..."
                )
                time.sleep(delay)
            else:
                logger.error(f"All {max_retries + 1} download attempts failed")
                raise


@PerformanceMonitor.monitor_operation("s3_upload", log_parameters=False)
def upload_to_s3_with_retry(
    file_obj, bucket_name: str, key: str, max_retries: int = 3
) -> None:
    """
    Upload file to S3 with retry logic for transient failures.

    Args:
        file_obj: File-like object to upload
        bucket_name: S3 bucket name
        key: S3 object key
        max_retries: Maximum number of retry attempts

    Raises:
        ClientError: If all retry attempts fail
    """
    for attempt in range(max_retries + 1):
        try:
            logger.info(f"S3 upload attempt {attempt + 1} to s3://{bucket_name}/{key}")
            s3_client.upload_fileobj(file_obj, bucket_name, key)
            logger.info(f"Successfully uploaded to S3: s3://{bucket_name}/{key}")
            return

        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            # Don't retry on certain errors
            if error_code in ["AccessDenied", "InvalidBucketName", "NoSuchBucket"]:
                logger.error(f"Non-retryable S3 error: {error_code}")
                raise

            if attempt < max_retries:
                delay = 1.0 * (2**attempt)
                logger.warning(
                    f"S3 upload attempt {attempt + 1} failed: {error_code}. Retrying in {delay}s..."
                )
                time.sleep(delay)
                # Reset file position for retry
                if hasattr(file_obj, "seek"):
                    file_obj.seek(0)
            else:
                logger.error(f"All {max_retries + 1} S3 upload attempts failed")
                raise


def get_pdf_from_api(paper_id: str) -> Optional[str]:
    """
    Fetches ArXiv PDF link using the Semantic Scholar API.

    Args:
        paper_id: Semantic Scholar paper ID

    Returns:
        PDF URL if found, None otherwise
    """
    url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}?fields=url,externalIds"
    headers = {}
    if API_KEY:
        headers["x-api-key"] = API_KEY

    timeout = float(config["HTTP_TIMEOUT_SECONDS"])

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        print(f"printing the request: {headers} ")
        resp.raise_for_status()
        data = resp.json()

        external_ids = data.get("externalIds", {})
        if "ArXiv" in external_ids:
            arxiv_id = external_ids["ArXiv"]
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            logger.info(f"Found PDF link via API: {pdf_url}")
            return pdf_url
        else:
            logger.warning(f"No ArXiv ID found for paper {paper_id}")
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch from Semantic Scholar API: {e}")
        return None


def extract_paper_id_from_url(pdf_url: str) -> Optional[str]:
    """
    Extracts the paper ID from a Semantic Scholar URL.

    Args:
        pdf_url: Semantic Scholar URL

    Returns:
        Paper ID if found, None otherwise
    """
    # Semantic Scholar paper IDs are 40-character hexadecimal strings
    match = re.search(r"/([0-9a-f]{40})$", pdf_url)
    if match:
        return match.group(1)
    return None


def get_pdf_link(pdf_url: str) -> Optional[str]:
    """
    If the URL is a Semantic Scholar page, try the API to get ArXiv PDF.

    Args:
        pdf_url: Semantic Scholar URL

    Returns:
        PDF URL if found, None otherwise
    """
    logger.info(f"Processing Semantic Scholar URL: {pdf_url}")
    paper_id = extract_paper_id_from_url(pdf_url)
    if not paper_id:
        logger.error(f"Could not extract paper ID from URL: {pdf_url}")
        return None
    return get_pdf_from_api(paper_id)


@StandardErrorHandler.handle_common_exceptions
def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Downloads a paper from a given URL and stores it in S3.

    Args:
        event: Lambda event containing pdf_url
        context: Lambda context

    Returns:
        Response with S3 path and metadata
    """
    logger.info(f"Received event: {json.dumps(event, default=str)}")

    # Parse request body
    body = RequestParser.parse_event_body(event)

    # Get PDF URL from body or direct event
    pdf_url = body.get("pdf_url") or event.get("pdf_url")

    # Validate required fields
    if not pdf_url:
        raise ValueError("Missing 'pdf_url' in request")

    # Validate URL format
    if not validate_url(pdf_url):
        raise ValueError(f"Invalid URL format: {pdf_url}")

    # Handle Semantic Scholar URLs
    if "semanticscholar.org" in pdf_url:
        new_pdf_url = get_pdf_link(pdf_url)
        if new_pdf_url:
            pdf_url = new_pdf_url
        else:
            return ResponseFormatter.create_error_response(
                404,
                "PDF Not Found",
                "Could not retrieve PDF link from Semantic Scholar page",
                f"Failed to resolve: {pdf_url}",
            )

    # Validate final PDF URL
    if not validate_url(pdf_url):
        raise ValueError(f"Invalid resolved PDF URL: {pdf_url}")

    # Generate sanitized filename
    parsed_url = urlparse(pdf_url)
    raw_filename = os.path.basename(parsed_url.path) or "paper.pdf"
    file_name = sanitize_filename(raw_filename)

    # Download the paper with retry logic and streaming
    logger.info(f"Downloading paper from: {pdf_url}")

    try:
        response = download_with_retry(pdf_url, max_retries=3, backoff_factor=1.0)

        # Validate content type if available
        content_type = response.headers.get("content-type", "").lower()
        if (
            content_type
            and "pdf" not in content_type
            and "application/octet-stream" not in content_type
        ):
            logger.warning(f"Unexpected content type: {content_type}")

        # Get content length for logging
        content_length = response.headers.get("content-length")
        if content_length:
            logger.info(f"Downloading {content_length} bytes")

        # Upload to S3 with retry logic and enhanced path validation
        bucket_name = config["RAW_BUCKET_NAME"]
        logger.info(f"Uploading to S3 bucket: {bucket_name}, Key: {file_name}")

        # Use streaming upload for memory efficiency
        upload_to_s3_with_retry(response.raw, bucket_name, file_name, max_retries=3)

        # Prepare response data with validated S3 path
        s3_path = f"s3://{bucket_name}/{file_name}"

        # Validate the constructed S3 path
        try:
            validate_s3_path(s3_path)
        except ValueError as e:
            logger.error(f"Invalid S3 path constructed: {e}")
            raise ValueError(f"Failed to construct valid S3 path: {e}")

        result = {
            "s3_path": s3_path,
            "file_name": file_name,
            "original_url": event.get("pdf_url", pdf_url),
            "resolved_url": pdf_url,
            "bucket_name": bucket_name,
        }

        # Include original event data if present
        if isinstance(event, dict):
            result.update({k: v for k, v in event.items() if k != "pdf_url"})

        logger.info(f"Successfully processed paper: {file_name}")
        return ResponseFormatter.create_success_response(result)

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else 502
        logger.error(f"HTTP error {status_code} for URL {pdf_url}: {e}")

        if 400 <= status_code < 500:
            return ResponseFormatter.create_error_response(
                status_code,
                "Client Error",
                f"Failed to download paper (HTTP {status_code})",
                str(e),
            )
        else:
            return ResponseFormatter.create_error_response(
                502,
                "Bad Gateway",
                "External server error while downloading paper",
                str(e),
            )

    except requests.exceptions.Timeout:
        logger.error(f"Timeout downloading from {pdf_url}")
        return ResponseFormatter.create_error_response(
            504, "Gateway Timeout", "Request timed out while downloading paper"
        )

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error downloading from {pdf_url}: {e}")
        return ResponseFormatter.create_error_response(
            502, "Bad Gateway", "Network error while downloading paper", str(e)
        )
