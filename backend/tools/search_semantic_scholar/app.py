import json
import requests


def lambda_handler(event, context):
    """
    Lambda function to search for papers on Semantic Scholar.

    Event body should be a JSON object with a "query" field.
    Example: {"query": "machine learning"}
    """
    try:
        body = json.loads(event.get("body", "{}"))
        query = body.get("query")

        if not query:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Query not provided."}),
            }

        # Call the Semantic Scholar API
        response = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": query, "limit": 3, "fields": "title,authors,abstract,url"},
        )
        response.raise_for_status()  # Raise an exception for bad status codes

        data = response.json()
        papers = data.get("data", [])

        # Format the results
        results = []
        for paper in papers:
            results.append(
                {
                    "title": paper.get("title"),
                    "authors": [author["name"] for author in paper.get("authors", [])],
                    "abstract": paper.get("abstract"),
                    "url": paper.get("url"),
                }
            )

        return {
            "statusCode": 200,
            "body": json.dumps(results),
        }

    except requests.exceptions.RequestException as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"API request failed: {e}"}),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }
