import os
import json
import logging
import boto3
import requests
from requests.exceptions import RequestException

# Initialize things outside of handler so reused across invocations
logger = logging.getLogger()
if not logger.handlers:
    import sys
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

SEMANTIC_SCHOLAR_BASE = os.environ.get(
    "SEMANTIC_SCHOLAR_BASE", "https://api.semanticscholar.org/graph/v1"
)
SEARCH_LIMIT = int(os.environ.get("SEARCH_LIMIT", "3"))
TIMEOUT = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "5"))
SECRET_NAME = os.environ.get("SECRET_NAME")

API_KEY = None
if SECRET_NAME:
    try:
        secrets_client = boto3.client("secretsmanager")
        secret_value = secrets_client.get_secret_value(SecretId=SECRET_NAME)
        # Assuming the secret is a JSON string with a key 'SEMANTIC_SCHOLAR_API_KEY'
        API_KEY = json.loads(secret_value["SecretString"]).get("SEMANTIC_SCHOLAR_API_KEY")
        if not API_KEY:
            logger.warning("SEMANTIC_SCHOLAR_API_KEY not found in secret.")
    except Exception as e:
        logger.error(f"Failed to retrieve API key from Secrets Manager: {e}")
        # Proceed without API key, will be subject to lower rate limits.
        API_KEY = None

def _make_request(url: str, params: dict, api_key: str = None):
    """Generic request helper for Semantic Scholar API."""
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    
    resp = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()

def search_paper(query: str, limit: int, fields: str, api_key: str = None):
    """Performs a keyword-based search for papers."""
    url = f"{SEMANTIC_SCHOLAR_BASE}/paper/search"
    params = {"query": query, "limit": limit, "fields": fields}
    return _make_request(url, params, api_key).get("data", [])

def get_paper(paper_id: str, fields: str, api_key: str = None):
    """Retrieves detailed information for a specific paper."""
    url = f"{SEMANTIC_SCHOLAR_BASE}/paper/{paper_id}"
    params = {"fields": fields}
    return _make_request(url, params, api_key)

def get_references(paper_id: str, fields: str, api_key: str = None):
    """Fetches the list of papers referenced by a given paper."""
    url = f"{SEMANTIC_SCHOLAR_BASE}/paper/{paper_id}/references"
    params = {"fields": fields}
    return _make_request(url, params, api_key).get("data", [])

def get_citations(paper_id: str, fields: str, api_key: str = None):
    """Fetches the list of papers that cite a given paper."""
    url = f"{SEMANTIC_SCHOLAR_BASE}/paper/{paper_id}/citations"
    params = {"fields": fields}
    return _make_request(url, params, api_key).get("data", [])


def lambda_handler(event, context):
    try:
        logger.info(f"Received event: {event}")
        body = json.loads(event.get("body", "{}"))
        
        action = body.get("action")
        if not action:
            return {"statusCode": 400, "body": json.dumps({"error": "Action not provided."})}

        results = None
        
        if action == "search_paper":
            query = body.get("query")
            if not query:
                return {"statusCode": 400, "body": json.dumps({"error": "Query not provided for search_paper."})}
            
            limit = body.get("limit", SEARCH_LIMIT)
            fields = body.get("fields", "title,authors,abstract,url")
            papers = search_paper(query, limit, fields, api_key=API_KEY)
            
            results = []
            for p in papers:
                results.append(
                    {
                        "title": p.get("title"),
                        "authors": [author.get("name") for author in p.get("authors", [])],
                        "abstract": p.get("abstract"),
                        "url": p.get("url"),
                    }
                )

        elif action in ["get_paper", "get_references", "get_citations"]:
            paper_id = body.get("paper_id")
            if not paper_id:
                return {"statusCode": 400, "body": json.dumps({"error": f"paper_id not provided for {action}."})}
            
            fields = body.get("fields", "title,authors,url") # Default fields for these actions

            if action == "get_paper":
                results = get_paper(paper_id, fields, api_key=API_KEY)
            elif action == "get_references":
                results = get_references(paper_id, fields, api_key=API_KEY)
            elif action == "get_citations":
                results = get_citations(paper_id, fields, api_key=API_KEY)
        else:
            return {"statusCode": 400, "body": json.dumps({"error": f"Invalid action: {action}"})}

        return {
            "statusCode": 200,
            "body": json.dumps(results),
        }

    except RequestException as e:
        # e.g. timeout, non-2xx response, network error
        logger.error(f"External request failed: {e}", exc_info=True)
        return {
            "statusCode": 502,
            "body": json.dumps(
                {"error": "External API request failed", "detail": str(e)}
            ),
        }
    except Exception as e:
        logger.exception("Unhandled exception in lambda_handler")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error", "detail": str(e)}),
        }