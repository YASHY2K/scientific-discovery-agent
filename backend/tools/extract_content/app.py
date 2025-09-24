import os
import json
import logging
import boto3
import fitz  # PyMuPDF
from typing import Dict, Any
import sys

sys.path.append("/opt/python")
from shared.lambda_utils import (
    setup_lambda_environment,
    RequestParser,
    ResponseFormatter,
    StandardErrorHandler,
    AWSClientManager,
    PerformanceMonitor,
    LambdaLogger,
)

# Initialize AWS clients outside handler for reuse
s3_client = AWSClientManager.get_client("s3")

# Environment variable configuration
REQUIRED_ENV_VARS = ["PROCESSED_BUCKET_NAME"]
OPTIONAL_ENV_VARS = {"TIMEOUT": "60", "MAX_FILE_SIZE_MB": "100"}


def parse_s3_path(s3_path: str) -> tuple[str, str]:
    """
    Parse S3 path into bucket and key components.

    Args:
        s3_path: S3 path in format s3://bucket/key

    Returns:
        Tuple of (bucket, key)

    Raises:
        ValueError: If S3 path format is invalid
    """
    if not s3_path.startswith("s3://"):
        raise ValueError("S3 path must start with 's3://'")

    path_parts = s3_path.replace("s3://", "").split("/", 1)
    if len(path_parts) != 2:
        raise ValueError("Invalid S3 path format. Expected: s3://bucket/key")

    bucket, key = path_parts
    if not bucket or not key:
        raise ValueError("S3 bucket and key cannot be empty")

    return bucket, key


@PerformanceMonitor.monitor_operation("pdf_extraction", log_parameters=False)
def extract_pdf_content(pdf_content: bytes, max_file_size_mb: int) -> Dict[str, Any]:
    """
    Extract text content and metadata from PDF using PyMuPDF with memory-efficient processing.

    Args:
        pdf_content: PDF file content as bytes
        max_file_size_mb: Maximum allowed file size in MB

    Returns:
        Dictionary containing extracted text and metadata

    Raises:
        ValueError: If PDF is invalid, corrupted, or too large
    """
    # Check file size
    file_size_mb = len(pdf_content) / (1024 * 1024)
    if file_size_mb > max_file_size_mb:
        raise ValueError(
            f"PDF file too large: {file_size_mb:.1f}MB exceeds limit of {max_file_size_mb}MB"
        )

    # Validate PDF content
    if not pdf_content or len(pdf_content) < 100:
        raise ValueError("PDF content is empty or too small to be valid")

    # Check PDF header
    if not pdf_content.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF format: missing PDF header")

    try:
        with fitz.open(stream=pdf_content, filetype="pdf") as doc:
            # Validate document
            if doc.is_closed:
                raise ValueError("PDF document could not be opened")

            if doc.page_count == 0:
                raise ValueError("PDF document contains no pages")

            # Extract basic metadata with error handling
            try:
                metadata = {
                    "page_count": doc.page_count,
                    "file_size_mb": round(file_size_mb, 2),
                    "title": doc.metadata.get("title", "").strip(),
                    "author": doc.metadata.get("author", "").strip(),
                    "subject": doc.metadata.get("subject", "").strip(),
                    "creator": doc.metadata.get("creator", "").strip(),
                    "producer": doc.metadata.get("producer", "").strip(),
                    "creation_date": doc.metadata.get("creationDate", ""),
                    "modification_date": doc.metadata.get("modDate", ""),
                    "is_encrypted": doc.needs_pass,
                    "is_pdf_a": doc.is_pdf,
                }
            except Exception as e:
                # If metadata extraction fails, continue with basic info
                metadata = {
                    "page_count": doc.page_count,
                    "file_size_mb": round(file_size_mb, 2),
                    "title": "",
                    "author": "",
                    "subject": "",
                    "creator": "",
                    "producer": "",
                    "creation_date": "",
                    "modification_date": "",
                    "is_encrypted": False,
                    "is_pdf_a": False,
                    "metadata_extraction_error": str(e),
                }

            # Memory-efficient text extraction - process pages in chunks
            full_text_parts = []
            page_texts = []
            failed_pages = []

            for page_num in range(doc.page_count):
                try:
                    page = doc[page_num]

                    # Extract text with error handling for corrupted pages
                    try:
                        page_text = page.get_text()
                        if page_text is None:
                            page_text = ""
                    except Exception as page_error:
                        page_text = f"[Error extracting text from page {page_num + 1}: {str(page_error)}]"
                        failed_pages.append(
                            {"page_number": page_num + 1, "error": str(page_error)}
                        )

                    page_info = {
                        "page_number": page_num + 1,
                        "text": page_text,
                        "char_count": len(page_text),
                    }
                    page_texts.append(page_info)
                    full_text_parts.append(page_text)

                    # Memory management for large documents
                    if page_num % 50 == 0 and page_num > 0:
                        # Force garbage collection every 50 pages for large documents
                        import gc

                        gc.collect()

                except Exception as e:
                    # Handle individual page processing errors
                    error_text = f"[Error processing page {page_num + 1}: {str(e)}]"
                    page_info = {
                        "page_number": page_num + 1,
                        "text": error_text,
                        "char_count": len(error_text),
                        "processing_error": str(e),
                    }
                    page_texts.append(page_info)
                    full_text_parts.append(error_text)
                    failed_pages.append({"page_number": page_num + 1, "error": str(e)})

            # Combine all text efficiently
            full_text = "\n".join(full_text_parts).strip()

            # Calculate text statistics
            total_chars = len(full_text)
            total_words = len(full_text.split()) if full_text else 0

            # Text quality assessment
            text_quality = {
                "has_text": total_chars > 0,
                "avg_chars_per_page": (
                    round(total_chars / doc.page_count, 2) if doc.page_count > 0 else 0
                ),
                "failed_pages_count": len(failed_pages),
                "success_rate": (
                    round(
                        (doc.page_count - len(failed_pages)) / doc.page_count * 100, 2
                    )
                    if doc.page_count > 0
                    else 0
                ),
            }

            result = {
                "full_text": full_text,
                "metadata": metadata,
                "text_statistics": {
                    "total_characters": total_chars,
                    "total_words": total_words,
                    "average_chars_per_page": text_quality["avg_chars_per_page"],
                },
                "text_quality": text_quality,
                "pages": page_texts,
            }

            # Add failed pages info if any
            if failed_pages:
                result["failed_pages"] = failed_pages

            return result

    except fitz.FileDataError as e:
        raise ValueError(f"PDF file is corrupted or invalid: {str(e)}")
    except fitz.FileNotFoundError as e:
        raise ValueError(f"PDF file could not be accessed: {str(e)}")
    except MemoryError as e:
        raise ValueError(f"PDF file too large to process in available memory: {str(e)}")
    except Exception as e:
        raise ValueError(f"Failed to process PDF: {str(e)}")


@StandardErrorHandler.handle_common_exceptions
def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Extract text content from PDF files using PyMuPDF.

    Expected input:
    {
        "s3_path": "s3://bucket/path/to/file.pdf"
    }

    Returns:
    {
        "full_text_s3_path": "s3://processed-bucket/path/full_text.txt",
        "metadata": {...},
        "text_statistics": {...}
    }
    """
    # Setup environment and logging
    config, logger = setup_lambda_environment(
        required_env_vars=REQUIRED_ENV_VARS,
        optional_env_vars=OPTIONAL_ENV_VARS,
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )

    logger.info(f"Processing extract content request")

    # Parse and validate request
    body = RequestParser.parse_event_body(event)
    RequestParser.validate_required_fields(body, ["s3_path"])

    s3_path = body["s3_path"]
    logger.info(f"Extracting content from: {s3_path}")

    # Parse S3 path
    source_bucket, source_key = parse_s3_path(s3_path)
    base_filename = os.path.splitext(source_key)[0]

    # Download PDF from S3 with comprehensive error handling
    logger.info(f"Downloading PDF from s3://{source_bucket}/{source_key}")
    try:
        # Check if object exists first
        try:
            s3_client.head_object(Bucket=source_bucket, Key=source_key)
        except s3_client.exceptions.NoSuchKey:
            raise ValueError(f"PDF file not found at {s3_path}")
        except s3_client.exceptions.NoSuchBucket:
            raise ValueError(f"S3 bucket '{source_bucket}' does not exist")

        # Download the object
        pdf_object = s3_client.get_object(Bucket=source_bucket, Key=source_key)

        # Validate content type if available
        content_type = pdf_object.get("ContentType", "")
        if content_type and not content_type.startswith("application/pdf"):
            logger.warning(
                f"File content type is '{content_type}', expected 'application/pdf'"
            )

        # Read content with size validation
        content_length = pdf_object.get("ContentLength", 0)
        max_size_bytes = int(config["MAX_FILE_SIZE_MB"]) * 1024 * 1024

        if content_length > max_size_bytes:
            raise ValueError(
                f"PDF file too large: {content_length / (1024*1024):.1f}MB exceeds limit"
            )

        pdf_content = pdf_object["Body"].read()

        if not pdf_content:
            raise ValueError("Downloaded PDF file is empty")

        logger.info(f"Successfully downloaded PDF: {len(pdf_content)} bytes")

    except ValueError:
        # Re-raise validation errors as-is
        raise
    except Exception as e:
        logger.error(f"Failed to download PDF from S3: {e}")
        error_msg = str(e)
        if "AccessDenied" in error_msg:
            raise ValueError(f"Access denied to S3 object {s3_path}")
        elif "NoCredentialsError" in error_msg:
            raise ValueError("AWS credentials not configured properly")
        else:
            raise ValueError(f"Could not download PDF from {s3_path}: {error_msg}")

    # Extract content using PyMuPDF
    logger.info("Extracting text content using PyMuPDF")
    max_file_size = int(config["MAX_FILE_SIZE_MB"])
    extraction_result = extract_pdf_content(pdf_content, max_file_size)

    # Store extracted text in processed bucket
    processed_bucket = config["PROCESSED_BUCKET_NAME"]
    full_text_key = f"{base_filename}/full_text.txt"

    logger.info(f"Uploading extracted text to s3://{processed_bucket}/{full_text_key}")
    try:
        # Validate processed bucket exists
        try:
            s3_client.head_bucket(Bucket=processed_bucket)
        except s3_client.exceptions.NoSuchBucket:
            raise ValueError(f"Processed bucket '{processed_bucket}' does not exist")

        # Prepare text content for upload
        text_content = extraction_result["full_text"]
        if not text_content:
            logger.warning("Extracted text is empty, uploading empty file")

        text_bytes = text_content.encode("utf-8")

        # Upload with metadata
        s3_client.put_object(
            Bucket=processed_bucket,
            Key=full_text_key,
            Body=text_bytes,
            ContentType="text/plain; charset=utf-8",
            Metadata={
                "source-s3-path": s3_path,
                "extraction-method": "PyMuPDF",
                "page-count": str(extraction_result["metadata"]["page_count"]),
                "character-count": str(
                    extraction_result["text_statistics"]["total_characters"]
                ),
                "word-count": str(extraction_result["text_statistics"]["total_words"]),
            },
        )

        logger.info(f"Successfully uploaded {len(text_bytes)} bytes to S3")

    except ValueError:
        # Re-raise validation errors as-is
        raise
    except Exception as e:
        logger.error(f"Failed to upload extracted text to S3: {e}")
        error_msg = str(e)
        if "AccessDenied" in error_msg:
            raise ValueError(f"Access denied to processed bucket '{processed_bucket}'")
        elif "NoCredentialsError" in error_msg:
            raise ValueError("AWS credentials not configured properly")
        else:
            raise ValueError(f"Could not upload extracted text: {error_msg}")

    # Prepare response with comprehensive information
    result = {
        "full_text_s3_path": f"s3://{processed_bucket}/{full_text_key}",
        "metadata": extraction_result["metadata"],
        "text_statistics": extraction_result["text_statistics"],
        "text_quality": extraction_result["text_quality"],
        "extraction_method": "PyMuPDF",
        "source_s3_path": s3_path,
    }

    # Add failed pages information if any
    if "failed_pages" in extraction_result:
        result["failed_pages"] = extraction_result["failed_pages"]
        logger.warning(
            f"Some pages failed to process: {len(extraction_result['failed_pages'])} out of {extraction_result['metadata']['page_count']}"
        )

    logger.info(
        f"Successfully extracted content. Text: {extraction_result['text_statistics']['total_characters']} chars, "
        f"Success rate: {extraction_result['text_quality']['success_rate']}%"
    )

    return ResponseFormatter.create_success_response(result)
