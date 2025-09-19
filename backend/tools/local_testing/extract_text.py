import os
import json
import logging
import requests
import io
import PyPDF2  # Ensure this is PyPDF2 v3.0.0+
import concurrent.futures  # For parallel processing in batch
from datetime import datetime
from urllib.parse import urlparse, urlunparse
from typing import Dict, Any, List

# Initialize logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Constants
DATA_DIR = os.environ.get("DATA_DIR", "/tmp")  # Use /tmp in Lambda
TIMEOUT = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "30"))


class PDFExtractionError(Exception):
    """Custom exception for PDF extraction errors"""

    pass


# NOTE: convert_arxiv_url_to_pdf is REMOVED from here.
# The agent will handle the conversion before calling this Lambda.


def extract_arxiv_metadata_from_pdf_url(pdf_url: str) -> Dict[str, Any]:
    """Extract metadata from a direct arXiv PDF URL."""
    parsed_url = urlparse(pdf_url)
    path_parts = parsed_url.path.strip("/").split("/")

    if len(path_parts) < 2 or not path_parts[-1].endswith(".pdf"):
        raise ValueError(f"Invalid arXiv PDF URL format: {pdf_url}")

    paper_id = path_parts[-1].replace(".pdf", "")

    # Attempt to derive the abstract URL from the PDF URL
    abs_path_parts = list(path_parts)
    if abs_path_parts[0] == "pdf":
        abs_path_parts[0] = "abs"
    abstract_url = urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            "/" + "/".join(abs_path_parts).replace(".pdf", ""),
            "",
            "",
            "",
        )
    )

    return {
        "paper_id": paper_id,
        "source": "arxiv",
        "pdf_url": pdf_url,
        "abstract_url": abstract_url,  # Store original abstract URL if available
        "extracted_timestamp": int(datetime.utcnow().timestamp()),
    }


def _extract_text_from_single_pdf(pdf_url: str) -> Dict[str, Any]:
    """Internal core logic to extract text from a single PDF URL."""
    try:
        logger.info(f"Downloading PDF from {pdf_url}")
        response = requests.get(pdf_url, timeout=TIMEOUT)
        response.raise_for_status()

        pdf_file = io.BytesIO(response.content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)

        pages = []
        for i, page in enumerate(pdf_reader.pages, 1):
            text = page.extract_text()
            pages.append({"page_number": i, "content": text, "char_count": len(text)})

        return {
            "status": "success",
            "pdf_url": pdf_url,
            "total_pages": len(pdf_reader.pages),
            "pages": pages,
            "total_chars": sum(page["char_count"] for page in pages),
        }

    except requests.RequestException as e:
        logger.error(f"Failed to download PDF {pdf_url}: {str(e)}")
        return {
            "status": "error",
            "pdf_url": pdf_url,
            "error_message": f"Failed to download PDF: {str(e)}",
        }
    except PyPDF2.errors.PdfReadError as e:  # <-- THE CRITICAL FIX for PyPDF2 v3.0.0+
        logger.error(f"Failed to read PDF {pdf_url}: {str(e)}")
        return {
            "status": "error",
            "pdf_url": pdf_url,
            "error_message": f"Failed to read PDF: {str(e)}",
        }
    except Exception as e:
        logger.exception(f"Unexpected error during PDF processing for {pdf_url}")
        return {
            "status": "error",
            "pdf_url": pdf_url,
            "error_message": f"Unexpected error: {str(e)}",
        }


def lambda_handler(event, context):
    """
    AWS Lambda handler that accepts a list of direct PDF URLs for batch processing.
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        body = json.loads(event.get("body", "{}"))
        pdf_urls: List[str] = body.get("pdf_urls")  # Expects a list of direct PDF URLs

        if not pdf_urls or not isinstance(pdf_urls, list):
            logger.warning("A JSON array of 'pdf_urls' must be provided")
            return {
                "statusCode": 400,
                "body": json.dumps(
                    {"error": "A JSON array of 'pdf_urls' must be provided"}
                ),
            }

        results = []
        # Use a ThreadPoolExecutor to download and process PDFs in parallel
        # Max workers set to 5, adjust based on Lambda memory/CPU and typical PDF count
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # Submitting tasks and collecting futures
            future_to_url = {
                executor.submit(_extract_text_from_single_pdf, url): url
                for url in pdf_urls
            }
            for future in concurrent.futures.as_completed(future_to_url):
                pdf_url = future_to_url[future]
                try:
                    single_result = future.result()
                    # Add metadata if extraction was successful
                    if single_result.get("status") == "success":
                        metadata = extract_arxiv_metadata_from_pdf_url(pdf_url)
                        results.append({**metadata, **single_result})
                    else:
                        results.append(single_result)  # Append error object directly
                except Exception as e:
                    logger.exception(f"Error getting result for {pdf_url}")
                    results.append(
                        {
                            "status": "error",
                            "pdf_url": pdf_url,
                            "error_message": f"Execution error: {str(e)}",
                        }
                    )

        return {"statusCode": 200, "body": json.dumps(results)}

    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON in request body"}),
        }
    except Exception as e:
        logger.exception("Unhandled exception in lambda_handler")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error", "detail": str(e)}),
        }


# --- Local Testing Code (Updated for batching) ---
class DummyContext:
    """Simulate AWS Lambda context object."""

    def __init__(self):
        self.function_name = "test-extract-content-function"
        self.aws_request_id = "test-request-id-12345"


def run_test_event(urls_list):
    """Run a test event with the given list of URLs."""
    event = {"body": json.dumps({"pdf_urls": urls_list})}
    context = DummyContext()

    print(f"=== Testing with URLs: '{urls_list}' ===")
    result = lambda_handler(event, context)
    print("Status Code:", result.get("statusCode"))

    body_str = result.get("body")
    if body_str:
        try:
            body_json = json.loads(body_str)
            print("Body:", json.dumps(body_json, indent=2))
        except json.JSONDecodeError:
            print("Body (non-JSON):", body_str)
    print()


if __name__ == "__main__":
    print("Running test cases for batch PDF extraction...")

    # Test with no URLs provided
    run_test_event(None)

    # Test with an empty list
    run_test_event([])

    # Test with a single valid arXiv PDF URL
    run_test_event(["https://arxiv.org/pdf/2310.01324.pdf"])

    # Test with multiple valid arXiv PDF URLs
    run_test_event(
        [
            "https://arxiv.org/pdf/2310.01324.pdf",
            "https://arxiv.org/pdf/2309.04394.pdf",  # Another LLM paper
        ]
    )

    # Test with a mix of valid and invalid URLs (e.g., non-existent PDF)
    run_test_event(
        [
            "https://arxiv.org/pdf/2310.01324.pdf",
            "https://arxiv.org/pdf/9999.99999.pdf",  # Non-existent
            "https://arxiv.org/pdf/2309.04394.pdf",
        ]
    )
