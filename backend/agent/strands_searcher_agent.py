import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
import boto3
from strands import Agent, tool
from agent.searcher_agent import create_searcher_agent

class StrandsSearcherAgent(Agent):
    def __init__(self, session_id: str = "default_session", lambda_client: Optional[boto3.client] = None, bedrock_client: Optional[boto3.client] = None, use_local_tools: bool = True):
        super().__init__(
            model="openai.gpt-oss-20b-1:0",
            system_prompt="You are a literature search expert. Your goal is to find papers."
        )
        self.logger = logging.getLogger(f"StrandsSearcherAgent-{session_id}")
        self.bedrock_client = bedrock_client or boto3.client("bedrock-runtime")
        self.searcher_agent = create_searcher_agent(
            session_id=session_id,
            lambda_client=lambda_client,
            logger=self.logger,
            use_local_tools=use_local_tools
        )
        self.logger.info(f"Strands Searcher Agent initialized (session: {session_id})")

    @tool
    async def search_literature(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """
        Uses a large language model to refine a search query, executes the search 
        across multiple academic databases, and returns a clean list of relevant papers.
        :param query: The high-level research topic to search for.
        :param limit: The maximum number of papers to return per database search.
        """
        self.logger.info(f"Intelligent search started for topic: '{query}'")
        refined_queries = await self._get_refined_queries(query)
        self.logger.info(f"Refined queries: {refined_queries}")

        search_tasks = [self.searcher_agent.search_literature(rq, limit) for rq in refined_queries]
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        all_papers = [p for res in search_results if not isinstance(res, Exception) for p in res.get("papers", [])]
        unique_papers = await self.searcher_agent._deduplicate_results(all_papers)
        
        self.logger.info(f"Found {len(unique_papers)} unique papers.")
        return {"query": query, "papers": unique_papers}

    async def _get_refined_queries(self, query: str) -> List[str]:
        prompt = f"You are a world-class academic researcher. Your task is to take a general research topic and generate 3 specific, keyword-rich search queries that are optimized for academic search engines like Google Scholar, ArXiv, and Semantic Scholar. Return ONLY a valid JSON array of strings, with nothing else before or after the array.\n\nTopic: '{query}'"
        body = json.dumps({
            "model": "openai.gpt-oss-20b-1:0",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 512,
        })
        try:
            response = await asyncio.to_thread(self.bedrock_client.invoke_model, body=body, modelId="openai.gpt-oss-20b-1:0")
            response_body = json.loads(response.get("body").read())
            content = response_body['choices'][0]['message']['content']
            return json.loads(content[content.find('['):content.rfind(']')+1])
        except Exception as e:
            self.logger.error(f"Bedrock query refinement failed: {e}. Falling back to original query.")
            return [query]

def create_strands_searcher_agent(**kwargs) -> StrandsSearcherAgent:
    return StrandsSearcherAgent(**kwargs)
