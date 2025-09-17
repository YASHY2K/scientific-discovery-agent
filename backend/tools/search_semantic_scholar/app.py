import os
import json
import logging
import requests
from requests.exceptions import RequestException

# Initialize things outside of handler so reused across invocations
logger = logging.getLogger()
logger.setLevel(logging.INFO)

SEMANTIC_SCHOLAR_BASE = os.environ.get(
    "SEMANTIC_SCHOLAR_BASE", "https://api.semanticscholar.org/graph/v1"
)
SEARCH_LIMIT = int(os.environ.get("SEARCH_LIMIT", "3"))
TIMEOUT = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "5"))


def search_papers(query: str):
    """Core logic to search papers from Semantic Scholar."""
    url = f"{SEMANTIC_SCHOLAR_BASE}/paper/search"
    params = {
        "query": query,
        "limit": SEARCH_LIMIT,
        "fields": "title,authors,abstract,url",
    }
    # Explicit timeout
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("data", [])


def lambda_handler(event, context):
    try:
        logger.info(f"Received event: {event}")
        body = json.loads(event.get("body", "{}"))
        query = body.get("query")

        if not query:
            logger.warning("Query not provided in request body.")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Query not provided."}),
            }

        papers = search_papers(query)
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
