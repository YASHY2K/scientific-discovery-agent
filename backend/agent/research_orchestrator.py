import logging
from typing import Optional, List, Dict, Any
import boto3
from strands import Agent, tool
from agent.strands_searcher_agent import create_strands_searcher_agent
from agent.strands_analyzer_agent import create_strands_analyzer_agent

class ResearchOrchestrator(Agent):
    def __init__(self, session_id: str = None, lambda_client: Optional[boto3.client] = None, use_local_tools: bool = True, log_level: int = logging.INFO, aws_profile: str = "hackathon-friend-role", aws_region: str = "us-east-1"):
        self.session_id = session_id or f"session_{int(time.time())}"
        self.use_local_tools = use_local_tools
        self.aws_profile = aws_profile
        self.aws_region = aws_region
        self.boto_session = boto3.Session(profile_name=self.aws_profile, region_name=self.aws_region)
        self.lambda_client = lambda_client or self.boto_session.client("lambda")
        bedrock_client = self.boto_session.client("bedrock-runtime")

        # Initialize specialist agents first, so their tools are available
        self.searcher_agent = create_strands_searcher_agent(session_id=self.session_id, lambda_client=self.lambda_client, bedrock_client=bedrock_client, use_local_tools=use_local_tools)
        self.analyzer_agent = create_strands_analyzer_agent(session_id=self.session_id, lambda_client=self.lambda_client, s3_client=self.boto_session.client("s3"), bedrock_client=bedrock_client, use_local_tools=use_local_tools)

        super().__init__(
            model="openai.gpt-oss-20b-1:0",
            system_prompt=self._get_system_prompt(),
            tools=[self.search_literature, self.analyze_papers]
        )
        
        self.logger = logging.getLogger(f"ResearchOrchestrator-{self.session_id}")
        self.logger.setLevel(log_level)
        self.logger.info(f"Research Orchestrator initialized (session: {self.session_id})")

    def _get_system_prompt(self) -> str:
        return (
            "You are a master research orchestrator. Your goal is to conduct research on a given topic. "
            "Follow these steps:\n"
            "1. Use your `search_literature` tool to find relevant academic papers on the user's topic.\n"
            "2. Once you have a list of papers, use your `analyze_papers` tool to process the top 3 most relevant ones.\n"
            "3. After the analysis is complete, present a final, comprehensive report to the user that includes the analysis summaries."
        )

    @tool
    async def search_literature(self, query: str) -> Dict[str, Any]:
        """
        Searches academic databases for relevant papers on a given topic.
        :param query: The research topic or query to search for.
        """
        self.logger.info(f"Delegating literature search for query: {query}")
        return await self.searcher_agent.search_literature(query=query)

    @tool
    async def analyze_papers(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Processes a list of papers to extract and synthesize their content.
        :param papers: A list of paper dictionary objects to be analyzed.
        """
        self.logger.info(f"Delegating analysis of {len(papers)} papers to AnalyzerAgent.")
        return await self.analyzer_agent.analyze_papers(papers=papers)

    async def process_message(self, message: str, context=None) -> str:
        self.logger.info(f"Orchestrator received message: '{message}'. Handing off to model-driven workflow.")
        return await self(message, context=context)

def create_research_orchestrator(**kwargs) -> ResearchOrchestrator:
    return ResearchOrchestrator(**kwargs)
