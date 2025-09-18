import os
import json
import logging
import requests
import io
import PyPDF2
from datetime import datetime
from urllib.parse import urlparse, urlunparse
from typing import Dict, Any

# Initialize logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Constants
DATA_DIR = os.environ.get("DATA_DIR", "/tmp")  # Use /tmp in Lambda
TIMEOUT = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "30"))


class PDFExtractionError(Exception):
    """Custom exception for PDF extraction errors"""

    pass


def convert_arxiv_url_to_pdf(url: str) -> str:
    """Convert an arXiv abstract URL to its corresponding PDF URL."""
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip("/").split("/")

    if len(path_parts) < 2:
        raise ValueError("Invalid arXiv URL format")

    if path_parts[0] == "abs":
        path_parts[0] = "pdf"
        if not path_parts[-1].endswith(".pdf"):
            path_parts[-1] = f"{path_parts[-1]}.pdf"

    new_path = "/" + "/".join(path_parts)
    return urlunparse((parsed_url.scheme, parsed_url.netloc, new_path, "", "", ""))


def extract_arxiv_metadata(url: str) -> Dict[str, Any]:
    """Extract metadata from an arXiv URL."""
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip("/").split("/")

    if len(path_parts) < 2:
        raise ValueError("Invalid arXiv URL format")

    paper_id = path_parts[-1].replace(".pdf", "")
    return {
        "paper_id": paper_id,
        "source": "arxiv",
        "url": url,
        "extracted_timestamp": int(datetime.utcnow().timestamp()),
        "pdf_url": convert_arxiv_url_to_pdf(url),
    }


def extract_text_from_pdf(url: str) -> Dict[str, Any]:
    """Core logic to extract text from a PDF URL."""
    try:
        # Download PDF with timeout
        logger.info(f"Downloading PDF from {url}")
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()

        # Create a file-like object from the downloaded content
        pdf_file = io.BytesIO(response.content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)

        # Extract text from all pages with structure
        pages = []
        for i, page in enumerate(pdf_reader.pages, 1):
            text = page.extract_text()
            pages.append({"page_number": i, "content": text, "char_count": len(text)})

        return {
            "total_pages": len(pdf_reader.pages),
            "pages": pages,
            "total_chars": sum(page["char_count"] for page in pages),
        }

    except requests.RequestException as e:
        raise PDFExtractionError(f"Failed to download PDF: {str(e)}")
    except PyPDF2.PdfReadError as e:
        raise PDFExtractionError(f"Failed to read PDF: {str(e)}")
    except Exception as e:
        raise PDFExtractionError(f"Unexpected error during PDF processing: {str(e)}")


def lambda_handler(event, context):
    """AWS Lambda handler function."""
    try:
        logger.info(f"Received event: {event}")
        body = json.loads(event.get("body", "{}"))
        url = body.get("url")

        if not url:
            logger.warning("URL not provided in request body")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "URL not provided"}),
            }

        # Get metadata
        metadata = extract_arxiv_metadata(url)

        # Extract PDF content
        content = extract_text_from_pdf(metadata["pdf_url"])

        # Combine results
        result = {**metadata, **content}

        return {"statusCode": 200, "body": json.dumps(result)}

    except ValueError as e:
        logger.error(f"Invalid input: {str(e)}")
        return {"statusCode": 400, "body": json.dumps({"error": str(e)})}
    except PDFExtractionError as e:
        logger.error(f"PDF extraction failed: {str(e)}")
        return {
            "statusCode": 502,
            "body": json.dumps({"error": "PDF extraction failed", "detail": str(e)}),
        }
    except Exception as e:
        logger.exception("Unhandled exception in lambda_handler")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error", "detail": str(e)}),
        }


class DummyContext:
    """Simulate AWS Lambda context object."""

    def __init__(self):
        self.function_name = "test-extract-content-function"
        self.aws_request_id = "test-request-id-12345"


def run_test_event(url_value):
    """Run a test event with the given URL."""
    event = {"body": json.dumps({"url": url_value})}
    context = DummyContext()

    print(f"=== Testing with URL: '{url_value}' ===")
    result = lambda_handler(event, context)
    print("Status Code:", result.get("statusCode"))

    # Pretty-print the JSON body
    body_str = result.get("body")
    if body_str:
        try:
            body_json = json.loads(body_str)
            print("Body:", json.dumps(body_json, indent=2))
        except json.JSONDecodeError:
            print("Body (non-JSON):", body_str)
    print()


if __name__ == "__main__":
    # Run test cases
    print("Running test cases...")

    # Test with no URL provided
    run_test_event(None)

    # Test with an empty URL string
    run_test_event("")

    # Test with a valid arXiv URL
    run_test_event("https://arxiv.org/abs/2310.01324")

    # Test with an invalid URL format
    run_test_event("https://example.com/not-an-arxiv-paper")
