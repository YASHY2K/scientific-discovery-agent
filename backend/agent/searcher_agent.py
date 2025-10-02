"""
Minimal Searcher Agent implementation for hackathon demonstration.

This agent serves as the intelligent literature discovery component within the
multi-agent research system. It coordinates searches across ArXiv and Semantic Scholar
using existing Lambda tools and provides basic result aggregation and filtering.

The agent supports two modes:
1. Local Mode: Direct function calls for development/testing
2. AWS Mode: Lambda service invocation for production deployment
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

import boto3

# Add paths for local tool imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Import local tools for direct invocation
try:
    from tools.search_arxiv.app import lambda_handler as arxiv_lambda_handler
    from tools.search_semantic_scholar.app import (
        lambda_handler as semantic_lambda_handler,
    )

    LOCAL_TOOLS_AVAILABLE = True
except ImportError as e:
    LOCAL_TOOLS_AVAILABLE = False
    # print(f"Warning: Local tools not available: {e}")


class DummyLambdaContext:
    """Mock Lambda context for local testing."""

    def __init__(self):
        self.aws_request_id = "local-test-request"

    def get_remaining_time_in_millis(self):
        return 300000


class SearcherAgent:
    """
    Minimal viable Searcher Agent for hackathon demonstration.
    Focuses on core functionality: multi-database search and basic filtering.
    """

    def __init__(
        self,
        lambda_client: Optional[boto3.client] = None,
        session_id: str = "default_session",
        logger: Optional[logging.Logger] = None,
        use_local_tools: bool = True,
    ):
        self.session_id = session_id
        self.logger = logger or logging.getLogger(f"SearcherAgent-{self.session_id}")
        self.use_local_tools = use_local_tools and LOCAL_TOOLS_AVAILABLE

        if self.use_local_tools:
            self.logger.info("SearcherAgent using local tool mode.")
            self.lambda_client = None
        else:
            self.logger.info("SearcherAgent using AWS Lambda service mode.")
            self.lambda_client = lambda_client or boto3.client("lambda")

        self.arxiv_function_name = "search_arxiv"
        self.semantic_scholar_function_name = "search_semantic_scholar"
        self.dummy_context = DummyLambdaContext()
        self.metrics = {"successful_tool_calls": 0, "failed_tool_calls": 0}

    async def search_literature(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Main search workflow."""
        self.logger.info(f"Starting literature search for query: '{query}'")
        start_time = time.time()

        arxiv_task = self._search_arxiv(query, limit)
        semantic_scholar_task = self._search_semantic_scholar(query, limit)

        results = await asyncio.gather(arxiv_task, semantic_scholar_task, return_exceptions=True)
        
        all_papers = []
        successful_searches = []
        failed_searches = []

        search_sources = [("ArXiv", results[0]), ("Semantic Scholar", results[1])]
        for source_name, result in search_sources:
            if isinstance(result, Exception):
                self.logger.warning(f"{source_name} search failed: {result}")
                failed_searches.append(source_name.lower())
            else:
                self.logger.info(f"{source_name} found {len(result)} papers.")
                all_papers.extend(result)
                successful_searches.append(source_name.lower())

        unique_papers = await self._deduplicate_results(all_papers)
        sorted_papers = self._sort_results(unique_papers)

        return {
            "query": query,
            "papers": sorted_papers,
            "metadata": {"search_duration_seconds": time.time() - start_time}
        }

    async def _deduplicate_results(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Simple deduplication based on title."""
        unique_papers = {}
        for paper in papers:
            title = paper.get("title", "").lower()
            if title and title not in unique_papers:
                unique_papers[title] = paper
        return list(unique_papers.values())

    def _sort_results(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort by year, descending."""
        return sorted(papers, key=lambda p: p.get("year", 0), reverse=True)

    def _create_search_event(self, query: str, limit: int) -> Dict[str, Any]:
        return {"body": json.dumps({"query": query, "limit": limit})}

    def _create_semantic_scholar_event(self, query: str, limit: int) -> Dict[str, Any]:
        return {"body": json.dumps({"action": "search_paper", "query": query, "limit": limit})}

    async def _invoke_tool(self, tool_name: str, event: Dict[str, Any]) -> Dict[str, Any]:
        if self.use_local_tools:
            handler = arxiv_lambda_handler if tool_name == self.arxiv_function_name else semantic_lambda_handler
            return await asyncio.get_event_loop().run_in_executor(None, lambda: handler(event, self.dummy_context))
        else:
            if not self.lambda_client:
                raise Exception("Lambda client not initialized for AWS mode.")
            return await self._invoke_lambda(tool_name, event)

    async def _invoke_lambda(self, function_name: str, event: Dict[str, Any]) -> Dict[str, Any]:
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.lambda_client.invoke(
                FunctionName=function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(event),
            ),
        )
        payload = json.loads(response["Payload"].read())
        if response.get("FunctionError"):
            raise Exception(f"Lambda {function_name} failed: {payload}")
        return payload

    async def _search_arxiv(self, query: str, limit: int) -> List[Dict[str, Any]]:
        event = self._create_search_event(query, limit)
        try:
            response = await self._invoke_tool(self.arxiv_function_name, event)
            if response.get("statusCode") == 200:
                body = json.loads(response.get("body", "{}"))
                return body.get("results", [])
        except Exception as e:
            self.logger.error(f"ArXiv tool failed: {e}")
        return []

    async def _search_semantic_scholar(self, query: str, limit: int) -> List[Dict[str, Any]]:
        event = self._create_semantic_scholar_event(query, limit)
        try:
            response = await self._invoke_tool(self.semantic_scholar_function_name, event)
            if response.get("statusCode") == 200:
                return json.loads(response.get("body", "[]"))
        except Exception as e:
            self.logger.error(f"Semantic Scholar tool failed: {e}")
        return []

def create_searcher_agent(
    session_id: str = "default_session",
    lambda_client: Optional[boto3.client] = None,
    logger: Optional[logging.Logger] = None,
    use_local_tools: bool = True,
) -> SearcherAgent:
    """
    Factory function to create a SearcherAgent instance.
    """
    return SearcherAgent(
        session_id=session_id,
        lambda_client=lambda_client,
        logger=logger,
        use_local_tools=use_local_tools,
    )
