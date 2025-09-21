import os
import json
import logging
import time
import requests
import xml.etree.ElementTree as ET
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

ARXIV_BASE = os.environ.get("ARXIV_BASE", "http://export.arxiv.org/api")
SEARCH_LIMIT = int(os.environ.get("SEARCH_LIMIT", "3"))
TIMEOUT = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "5"))


def search_papers(query: str):
    """Core logic to search papers from ArXiv."""
    # Enforce rate limit
    time.sleep(3)

    url = f"{ARXIV_BASE}/query"
    params = {
        "search_query": query,
        "max_results": SEARCH_LIMIT,
    }
    # Explicit timeout
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()

    # ArXiv API returns XML, so we need to parse it
    root = ET.fromstring(resp.content)

    # Namespace for Atom feed
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    papers = []
    for entry in root.findall("atom:entry", ns):
        title = entry.find("atom:title", ns).text.strip()

        authors = [
            author.find("atom:name", ns).text
            for author in entry.findall("atom:author", ns)
        ]

        # The 'summary' tag contains the abstract
        abstract = entry.find("atom:summary", ns).text.strip()

        # Find the PDF link, which has rel="related" and type="application/pdf"
        pdf_url = ""
        for link in entry.findall("atom:link", ns):
            if link.get("rel") == "related" and link.get("type") == "application/pdf":
                pdf_url = link.get("href")
                break

        # The 'id' tag is a permalink to the paper, use as fallback
        if not pdf_url:
            pdf_url = entry.find("atom:id", ns).text.strip()

        papers.append(
            {
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "url": pdf_url,
            }
        )
    return papers


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

        results = search_papers(query)

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
