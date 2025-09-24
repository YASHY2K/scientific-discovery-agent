import time
import requests
import xml.etree.ElementTree as ET
from requests.exceptions import RequestException, Timeout
from typing import Dict, Any, List
import sys
import os

# Add the shared utilities to the path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "shared"))

# Import shared utilities
from shared.lambda_utils import (
    setup_lambda_environment,
    RequestParser,
    ResponseFormatter,
    StandardErrorHandler,
    PerformanceMonitor,
    LambdaLogger,
)

# Environment configuration
REQUIRED_ENV_VARS = []  # No required vars for ArXiv search
OPTIONAL_ENV_VARS = {
    "ARXIV_BASE": "http://export.arxiv.org/api",
    "SEARCH_LIMIT": "3",
    "TIMEOUT": "5",
    "LOG_LEVEL": "INFO",
}

# Setup environment (done outside handler for reuse)
config, logger = setup_lambda_environment(
    required_env_vars=REQUIRED_ENV_VARS,
    optional_env_vars=OPTIONAL_ENV_VARS,
    log_level=OPTIONAL_ENV_VARS["LOG_LEVEL"],
)


@PerformanceMonitor.monitor_operation("arxiv_search", log_parameters=False)
def search_papers(query: str, limit: int = None) -> List[Dict[str, Any]]:
    """
    Core logic to search papers from ArXiv.

    Args:
        query: Search query string
        limit: Maximum number of results (optional)

    Returns:
        List of paper dictionaries

    Raises:
        RequestException: If ArXiv API request fails
        Timeout: If request times out
    """
    # Use provided limit or default from config
    search_limit = limit if limit is not None else int(config["SEARCH_LIMIT"])

    # Enforce rate limit for ArXiv API compliance
    logger.info("Enforcing 3-second rate limit for ArXiv API")
    time.sleep(3)

    url = f"{config['ARXIV_BASE']}/query"
    params = {
        "search_query": query,
        "max_results": search_limit,
    }

    logger.info(f"Searching ArXiv with query: {query}, limit: {search_limit}")

    # Make request with explicit timeout
    timeout = float(config["TIMEOUT"])
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()

    # Parse ArXiv XML response
    root = ET.fromstring(resp.content)
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    papers = []
    for entry in root.findall("atom:entry", ns):
        title = entry.find("atom:title", ns).text.strip()

        authors = [
            author.find("atom:name", ns).text
            for author in entry.findall("atom:author", ns)
        ]

        abstract = entry.find("atom:summary", ns).text.strip()

        # Find PDF link
        pdf_url = ""
        for link in entry.findall("atom:link", ns):
            if link.get("rel") == "related" and link.get("type") == "application/pdf":
                pdf_url = link.get("href")
                break

        # Use permalink as fallback
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

    logger.info(f"Found {len(papers)} papers for query: {query}")
    return papers


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda handler for ArXiv paper search using standardized utilities.

    Args:
        event: Lambda event dictionary
        context: Lambda context object

    Returns:
        Standardized Lambda response
    """
    try:
        logger.info("Received ArXiv search request")

        # Parse and validate request
        body = RequestParser.parse_event_body(event)
        RequestParser.validate_required_fields(body, ["query"])

        # Extract parameters
        query = body["query"]
        limit = body.get("limit")  # Optional parameter

        # Validate query
        if not query or not query.strip():
            raise ValueError("Query cannot be empty or whitespace only")

        if len(query) > 500:
            raise ValueError("Query must be 500 characters or less")

        # Validate limit if provided
        if limit is not None:
            try:
                limit = int(limit)
                if limit <= 0 or limit > 100:
                    raise ValueError("Limit must be between 1 and 100")
            except (ValueError, TypeError):
                raise ValueError("Limit must be a valid positive integer")

        logger.info(f"Processing ArXiv search: query='{query}', limit={limit}")

        # Execute search with performance monitoring
        try:
            results = search_papers(query, limit)

            # Log search metrics
            LambdaLogger.log_performance_metrics(
                logger,
                "arxiv_search_complete",
                0,
                True,
                query_length=len(query),
                results_count=len(results),
                search_limit=limit or int(config["SEARCH_LIMIT"]),
            )

        except Timeout:
            LambdaLogger.log_structured_error(
                logger,
                TimeoutError("ArXiv API timeout"),
                "arxiv_search",
                "timeout",
                query=query,
                timeout_seconds=config["TIMEOUT"],
            )
            return ResponseFormatter.create_error_response(
                504,
                "Gateway Timeout",
                "ArXiv API request timed out",
                f"Request exceeded {config['TIMEOUT']} second timeout",
            )
        except RequestException as e:
            LambdaLogger.log_structured_error(
                logger,
                e,
                "arxiv_search",
                "api_error",
                query=query,
                api_base=config["ARXIV_BASE"],
            )
            return ResponseFormatter.create_error_response(
                502, "Bad Gateway", "ArXiv API request failed", str(e)
            )

        # Return success response with metadata
        return ResponseFormatter.create_success_response(
            {
                "query": query,
                "results": results,
                "metadata": {
                    "count": len(results),
                    "limit": limit or int(config["SEARCH_LIMIT"]),
                    "source": "ArXiv",
                    "api_base": config["ARXIV_BASE"],
                },
            }
        )

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return ResponseFormatter.create_error_response(400, "Validation Error", str(e))
    except Exception as e:
        logger.exception("Unexpected error in ArXiv search")
        return ResponseFormatter.create_error_response(
            500,
            "Internal Server Error",
            "An unexpected error occurred during ArXiv search",
            str(e),
        )
