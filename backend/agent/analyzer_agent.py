
"""
Analyzer Agent for the Multi-Agent Research System

This agent is responsible for processing a list of academic papers by
orchestrating a series of tools to acquire, extract, and preprocess their content.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import boto3

# Assuming shared utilities and tool invocation logic will be needed
from searcher_agent import SearcherAgent


class AnalyzerAgent(SearcherAgent):
    """
    The AnalyzerAgent processes scientific papers by orchestrating a sequence of
    document processing tools. It extends SearcherAgent to reuse tool invocation logic.
    """

    def __init__(
        self,
        lambda_client: Optional[boto3.client] = None,
        s3_client: Optional[boto3.client] = None,
        bedrock_client: Optional[boto3.client] = None,
        session_id: str = "default_session",
        logger: Optional[logging.Logger] = None,
        use_local_tools: bool = True,
    ):
        """
        Initializes the AnalyzerAgent.
        """
        super().__init__(
            lambda_client=lambda_client,
            session_id=session_id,
            logger=logger,
            use_local_tools=use_local_tools,
        )
        self.s3_client = s3_client or boto3.client("s3")
        self.bedrock_client = bedrock_client or boto3.client("bedrock-runtime")

        # Define the names of the document processing Lambda functions
        self.acquire_paper_function_name = "acquire_paper"
        self.extract_content_function_name = "extract_content"
        self.preprocess_text_function_name = "preprocess_text"

        self.logger.info(f"Analyzer Agent initialized (session: {self.session_id})")

    async def analyze_papers(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Orchestrates the analysis of the top N papers.

        Args:
            papers: A list of paper dictionaries from the SearcherAgent.

        Returns:
            An updated list of paper dictionaries, enriched with analysis.
        """
        self.logger.info(f"Starting analysis for {len(papers)} papers.")
        
        # For the MVP, we will only process the top 3 papers to manage time and cost
        top_papers = papers[:3]
        
        analysis_tasks = [self._process_single_paper(paper) for paper in top_papers]
        processed_papers = await asyncio.gather(*analysis_tasks, return_exceptions=True)

        # Filter out papers that failed processing
        successful_papers = [p for p in processed_papers if not isinstance(p, Exception)]
        
        if not successful_papers:
            raise Exception("AnalyzerAgent failed to process any papers.")
        
        self.logger.info(f"Successfully processed and analyzed {len(successful_papers)} papers.")
        
        # Return the original list of papers, with the top ones now enriched
        return successful_papers

    async def _process_single_paper(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes a single paper through the acquire-extract-preprocess pipeline.
        """
        paper_url = paper.get("url")
        if not paper_url:
            raise ValueError("Paper dictionary must contain a 'url' field.")

        self.logger.info(f"Processing paper: {paper.get('title', paper_url)}")

        # Step 1: Acquire Paper
        acquired_event = {"body": json.dumps({"pdf_url": paper_url})}
        acquired_result = await self._invoke_tool(self.acquire_paper_function_name, acquired_event)
        self.logger.info(f"Acquired paper result: {acquired_result}")
        s3_path = acquired_result.get("s3_path")
        if not s3_path:
            raise Exception(f"Failed to acquire paper from {paper_url}. Result: {acquired_result}")

        # Step 2: Extract Content
        extracted_event = {"body": json.dumps({"s3_path": s3_path})}
        extracted_result = await self._invoke_tool(self.extract_content_function_name, extracted_event)
        self.logger.info(f"Extracted content result: {extracted_result}")
        text_s3_path = extracted_result.get("full_text_s3_path")
        if not text_s3_path:
            raise Exception(f"Failed to extract content from {s3_path}. Result: {extracted_result}")

        # Step 3: Preprocess Text
        preprocessed_event = {"body": json.dumps({"full_text_s3_path": text_s3_path})}
        preprocessed_result = await self._invoke_tool(self.preprocess_text_function_name, preprocessed_event)
        self.logger.info(f"Preprocessed text result: {preprocessed_result}")
        chunks_s3_path = preprocessed_result.get("chunks_s3_path")
        if not chunks_s3_path:
            raise Exception(f"Failed to preprocess text from {text_s3_path}. Result: {preprocessed_result}")
            
        # Step 4: Synthesize Findings
        self.logger.info(f"Synthesizing findings for paper: {paper.get('title')}")
        bucket, key = chunks_s3_path.replace("s3://", "").split("/", 1)
        chunks_obj = self.s3_client.get_object(Bucket=bucket, Key=key)
        chunks_data = json.loads(chunks_obj["Body"].read().decode("utf-8"))
        
        full_text = " ".join(chunks_data.get("chunks", []))
        
        synthesis = await self._synthesize_with_bedrock(full_text)
        paper["analysis_summary"] = synthesis
        
        self.logger.info(f"Successfully synthesized findings for: {paper.get('title')}")

        return paper

    async def _synthesize_with_bedrock(self, text: str) -> str:
        """
        Uses Bedrock (OpenAI) to synthesize the text.
        """
        prompt = f"You are an expert research assistant. Please read the following text from a scientific paper and provide a concise summary of its key findings, methodology, and conclusions. Focus on the most critical information.\n\n<document>{text[:20000]}</document>"
        
        body = json.dumps({
            "model": "openai.gpt-oss-20b-1:0",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
        })

        try:
            response = await asyncio.to_thread(
                self.bedrock_client.invoke_model,
                body=body,
                modelId="openai.gpt-oss-20b-1:0",
                accept="application/json",
                contentType="application/json"
            )
            response_body = json.loads(response.get("body").read())
            return response_body['choices'][0]['message']['content']
        except Exception as e:
            self.logger.error(f"Bedrock synthesis failed: {e}")
            return "Error: Could not synthesize the paper's content."

