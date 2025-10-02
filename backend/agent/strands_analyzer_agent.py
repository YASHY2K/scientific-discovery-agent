import logging
from typing import Any, Dict, List, Optional
import boto3
from strands import Agent, tool
from agent.analyzer_agent import AnalyzerAgent

class StrandsAnalyzerAgent(Agent):
    def __init__(self, session_id: str = "default_session", lambda_client: Optional[boto3.client] = None, s3_client: Optional[boto3.client] = None, bedrock_client: Optional[boto3.client] = None, use_local_tools: bool = True):
        super().__init__(
            model="openai.gpt-oss-20b-1:0",
            system_prompt="You are a paper analysis expert. Your goal is to process and summarize papers."
        )
        self.logger = logging.getLogger(f"StrandsAnalyzerAgent-{session_id}")
        self.analyzer_agent = AnalyzerAgent(
            session_id=session_id,
            lambda_client=lambda_client,
            s3_client=s3_client,
            bedrock_client=bedrock_client,
            use_local_tools=use_local_tools,
            logger=self.logger
        )
        self.logger.info(f"Strands Analyzer Agent initialized (session: {session_id})")

    @tool
    async def analyze_papers(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Takes a list of papers, runs them through a processing pipeline (acquire, extract, 
        preprocess), and generates a concise analysis summary for each.
        :param papers: A list of paper dictionary objects to be analyzed.
        """
        self.logger.info(f"Analysis tool invoked for {len(papers)} papers.")
        enriched_papers = await self.analyzer_agent.analyze_papers(papers)
        return {"papers": enriched_papers}

def create_strands_analyzer_agent(**kwargs) -> StrandsAnalyzerAgent:
    return StrandsAnalyzerAgent(**kwargs)
