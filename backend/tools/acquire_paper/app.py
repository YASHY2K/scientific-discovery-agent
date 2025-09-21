import os
import json
import logging
import boto3
import requests
import time
from urllib.parse import urlparse
import re
from dotenv import load_dotenv

# Load environment variables from .env file for local development
load_dotenv()

# Initialize AWS clients
s3 = boto3.client("s3")

# Initialize logging
logger = logging.getLogger()
if not logger.handlers:
    import sys
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Environment variables
RAW_BUCKET_NAME = os.environ.get("RAW_BUCKET_NAME")
TIMEOUT = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "60"))
SECRET_NAME = os.environ.get("SECRET_NAME")
API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")  # From .env for local

# If running in AWS and SECRET_NAME is set, fetch from Secrets Manager
if SECRET_NAME:
    try:
        secrets_client = boto3.client("secretsmanager")
        secret_value = secrets_client.get_secret_value(SecretId=SECRET_NAME)
        secret_data = json.loads(secret_value["SecretString"])
        API_KEY = secret_data.get("SEMANTIC_SCHOLAR_API_KEY")
        if not API_KEY:
            logger.warning("SEMANTIC_SCHOLAR_API_KEY not found in secret, proceeding without API key.")
        else:
            logger.info("Successfully loaded Semantic Scholar API key from Secrets Manager.")
    except Exception as e:
        logger.error(f"Failed to retrieve API key from Secrets Manager: {e}. Proceeding without API key.")
        API_KEY = None
elif API_KEY:
    logger.info("Loaded Semantic Scholar API key from environment/.env file.")
else:
    logger.warning("Semantic Scholar API key not found in environment or Secrets Manager. Proceeding without API key.")


def get_pdf_from_api(paper_id: str):
    """
    Fetches ArXiv PDF link using the Semantic Scholar API.
    """
    url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}?fields=url,externalIds"
    headers = {}
    if API_KEY:
        headers["x-api-key"] = API_KEY
        
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if "ArXiv" in data.get("externalIds", {}):
            arxiv_id = data["externalIds"]["ArXiv"]
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            logger.info(f"Found PDF link via API: {pdf_url}")
            return pdf_url
        else:
            logger.warning("No ArXiv ID found in externalIds.")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch from API: {e}")
        return None


def extract_paper_id_from_url(pdf_url: str):
    """
    Extracts the paper ID from a Semantic Scholar URL.
    """
    match = re.search(r"/([0-9a-f]{40})$", pdf_url)
    if match:
        return match.group(1)
    return None


def get_pdf_link(pdf_url: str):
    """
    If the URL is a Semantic Scholar page, try the API to get ArXiv PDF.
    """
    logger.info(f"Semantic Scholar URL detected: {pdf_url}")
    paper_id = extract_paper_id_from_url(pdf_url)
    if not paper_id:
        logger.error("Could not extract paper ID from URL.")
        return None
    return get_pdf_from_api(paper_id)


def lambda_handler(event, context):
    """
    Downloads a paper from a given URL and stores it in S3.
    """
    pdf_url = event.get("pdf_url")
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        # Validate PDF URL
        if not pdf_url:
            logger.error("Validation Error: Missing 'pdf_url' in the event payload.")
            return {
                "statusCode": 400,
                "body": json.dumps(
                    {"error": "Missing 'pdf_url' in the event payload."}
                ),
            }

        # Validate environment variable
        if not RAW_BUCKET_NAME:
            logger.error(
                "Configuration Error: RAW_BUCKET_NAME environment variable not set."
            )
            return {
                "statusCode": 500,
                "body": json.dumps(
                    {"error": "Server configuration error: S3 bucket name not set."}
                ),
            }

        if "semanticscholar.org" in pdf_url:
            new_pdf_url = get_pdf_link(pdf_url)
            if new_pdf_url:
                pdf_url = new_pdf_url
            else:
                logger.error(
                    f"Could not retrieve PDF link from Semantic Scholar API for {pdf_url}"
                )
                return {
                    "statusCode": 404,
                    "body": json.dumps(
                        {"error": "PDF link not found on Semantic Scholar page."}
                    ),
                }

        # Generate a filename from the URL
        parsed_url = urlparse(pdf_url)
        file_name = os.path.basename(parsed_url.path)
        if not file_name.endswith(".pdf"):
            file_name += ".pdf"

        # Download the paper
        logger.info(f"Downloading paper from: {pdf_url}")
        response = requests.get(pdf_url, timeout=TIMEOUT, stream=True)
        response.raise_for_status()  # Raises HTTPError for 4xx/5xx responses

        # Upload to S3
        logger.info(
            f"Uploading paper to S3 bucket: {RAW_BUCKET_NAME}, Key: {file_name}"
        )
        s3.upload_fileobj(response.raw, RAW_BUCKET_NAME, file_name)

        # Augment the original event with the new S3 path and return
        event["s3_path"] = f"s3://{RAW_BUCKET_NAME}/{file_name}"
        event["file_name"] = file_name

        return {"statusCode": 200, "body": json.dumps(event)}

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        logger.error(f"HTTP error {status_code} for URL {pdf_url}: {e}")
        return {
            "statusCode": status_code if 400 <= status_code < 500 else 502,
            "body": json.dumps(
                {
                    "error": f"Failed to download paper, received status: {status_code}",
                    "details": str(e),
                }
            ),
        }
    except requests.exceptions.Timeout:
        logger.error(f"Timeout while trying to download from {pdf_url}")
        return {
            "statusCode": 504,
            "body": json.dumps(
                {"error": "Gateway Timeout: The request to the external URL timed out."}
            ),
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error downloading paper from {pdf_url}: {e}")
        return {
            "statusCode": 502,
            "body": json.dumps(
                {
                    "error": "Bad Gateway: A network error occurred while fetching the paper.",
                    "details": str(e),
                }
            ),
        }
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"error": "An internal server error occurred.", "details": str(e)}
            ),
        }
