import os
import json
import logging
import boto3
import re
from langchain.text_splitter import RecursiveCharacterTextSplitter

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

# Environment variables from Lambda configuration
PROCESSED_BUCKET_NAME = os.environ.get("PROCESSED_BUCKET_NAME")
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 1000))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", 200))


def clean_text(text: str) -> str:
    """
    Cleans raw text by removing common PDF extraction artifacts and normalizing whitespace.
    This function avoids aggressive NLP techniques like stemming or stop-word removal.
    """
    # A more robust regex for page numbers and other header/footer-like patterns
    text = re.sub(r"^\s*Page \d+\s*$", "", text, flags=re.MULTILINE)
    # Normalize whitespace: replace multiple spaces/newlines with a single space
    text = re.sub(r"\s+", " ", text).strip()
    # Remove characters that are often a result of decoding errors
    text = text.replace("\ufffd", "")
    return text


def lambda_handler(event, context):
    """
    Handles the text preprocessing stage: downloads extracted text from S3,
    cleans it, splits it into semantic chunks, and uploads the chunks back to S3.
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        artifacts = event.get("artifacts", {})
        full_text_s3_path = artifacts.get("full_text_s3_path")

        if not full_text_s3_path:
            raise ValueError("'full_text_s3_path' not found in event artifacts.")

        if not PROCESSED_BUCKET_NAME:
            raise ValueError("PROCESSED_BUCKET_NAME environment variable is not set.")

        # Parse S3 path
        bucket, key = full_text_s3_path.replace("s3://", "").split("/", 1)
        base_path = os.path.dirname(key)

        # Download the full text
        logger.info(f"Downloading text from s3://{bucket}/{key}")
        text_object = s3.get_object(Bucket=bucket, Key=key)
        raw_text = text_object["Body"].read().decode("utf-8")

        # Clean the text
        logger.info("Cleaning extracted text.")
        cleaned_text = clean_text(raw_text)

        # Initialize the recursive text splitter
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
        )  # Prioritizes paragraphs

        # Create chunks
        logger.info(f"Chunking text into pieces of ~{CHUNK_SIZE} characters.")
        chunks = text_splitter.split_text(cleaned_text)

        # Store chunks in a structured JSON object
        chunks_data = {
            "parent_document": full_text_s3_path,
            "chunking_strategy": "RecursiveCharacterTextSplitter",
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
            "chunk_count": len(chunks),
            "chunks": chunks,
        }

        chunks_key = f"{base_path}/chunks.json"
        logger.info(
            f"Uploading {len(chunks)} chunks to s3://{PROCESSED_BUCKET_NAME}/{chunks_key}"
        )
        s3.put_object(
            Bucket=PROCESSED_BUCKET_NAME,
            Key=chunks_key,
            Body=json.dumps(chunks_data, indent=2).encode("utf-8"),
            ContentType="application/json",
        )

        # Update event with the new artifact path
        event["artifacts"][
            "chunks_s3_path"
        ] = f"s3://{PROCESSED_BUCKET_NAME}/{chunks_key}"

        return {"statusCode": 200, "body": json.dumps(event)}

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"error": "An internal server error occurred.", "details": str(e)}
            ),
        }
