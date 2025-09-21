import os
import json
import logging
import boto3
import fitz  # PyMuPDF
import requests
import xmltodict

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
PROCESSED_BUCKET_NAME = os.environ.get("PROCESSED_BUCKET_NAME")
GROBID_URL = os.environ.get("GROBID_URL")
TIMEOUT = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "60"))

def lambda_handler(event, context):
    """
    Extracts content from a PDF using PyMuPDF and an external GROBID service.
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        s3_path = event.get('s3_path')
        if not s3_path:
            raise ValueError("Missing 's3_path' in the event payload.")

        if not PROCESSED_BUCKET_NAME or not GROBID_URL:
            raise ValueError("PROCESSED_BUCKET_NAME and GROBID_URL environment variables must be set.")

        # Parse bucket and key from S3 path
        raw_bucket, key = s3_path.replace("s3://", "").split("/", 1)
        base_filename = os.path.splitext(key)[0]

        # Download PDF from S3
        logger.info(f"Downloading PDF from s3://{raw_bucket}/{key}")
        pdf_object = s3.get_object(Bucket=raw_bucket, Key=key)
        pdf_content = pdf_object['Body'].read()

        # 1. Full text extraction with PyMuPDF
        logger.info("Extracting full text using PyMuPDF.")
        full_text = ""
        with fitz.open(stream=pdf_content, filetype="pdf") as doc:
            full_text = "".join(page.get_text() for page in doc)
        
        full_text_key = f"{base_filename}/full_text.txt"
        logger.info(f"Uploading full text to s3://{PROCESSED_BUCKET_NAME}/{full_text_key}")
        s3.put_object(Bucket=PROCESSED_BUCKET_NAME, Key=full_text_key, Body=full_text.encode('utf-8'))

        # 2. Bibliographic data extraction with GROBID
        logger.info(f"Extracting metadata using GROBID service at {GROBID_URL}")
        response = requests.post(
            f"{GROBID_URL}/api/processHeaderDocument",
            files={"input": (key, pdf_content, "application/pdf")},
            timeout=TIMEOUT
        )
        response.raise_for_status()

        metadata_json = xmltodict.parse(response.text)
        metadata_key = f"{base_filename}/metadata.json"
        logger.info(f"Uploading metadata to s3://{PROCESSED_BUCKET_NAME}/{metadata_key}")
        s3.put_object(Bucket=PROCESSED_BUCKET_NAME, Key=metadata_key, Body=json.dumps(metadata_json, indent=2).encode('utf-8'))

        # Append artifact paths to the event
        event['artifacts'] = {
            'full_text_s3_path': f"s3://{PROCESSED_BUCKET_NAME}/{full_text_key}",
            'metadata_s3_path': f"s3://{PROCESSED_BUCKET_NAME}/{metadata_key}"
        }

        return {
            "statusCode": 200,
            "body": json.dumps(event)
        }

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "An internal server error occurred.", "details": str(e)})
        }
