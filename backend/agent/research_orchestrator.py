import logging
from typing import Optional, List, Dict, Any
import boto3
from strands import Agent, tool
from strands.models import BedrockModel

from utils import get_ssm_parameter
from agent.agentcore_memory import (
    AgentCoreMemoryHook,
    memory_client,
    ACTOR_ID,
    SESSION_ID,
)
from planner_agent import planner_agent, ResearchPlan
from searcher_agent import searcher_agent, format_search_query
import json

logging.getLogger("strands").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s", handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

# class ResearchOrchestrator(Agent):
#     def __init__(
#         self,
#         session_id: str = None,
#         lambda_client: Optional[boto3.client] = None,
#         use_local_tools: bool = True,
#         log_level: int = logging.INFO,
#         aws_region: str = "us-east-1",
#     ):
#         # self.session_id = session_id or f"session_{int(time.time())}"
#         self.use_local_tools = use_local_tools
#         self.aws_region = aws_region
#         self.boto_session = boto3.Session(region_name=self.aws_region)
#         self.lambda_client = lambda_client or self.boto_session.client("lambda")
#         bedrock_client = self.boto_session.client("bedrock-runtime")

#         # Initialize specialist agents first, so their tools are available
#         self.searcher_agent = create_strands_searcher_agent(
#             session_id=self.session_id,
#             lambda_client=self.lambda_client,
#             bedrock_client=bedrock_client,
#             use_local_tools=use_local_tools,
#         )
#         self.analyzer_agent = create_strands_analyzer_agent(
#             session_id=self.session_id,
#             lambda_client=self.lambda_client,
#             s3_client=self.boto_session.client("s3"),
#             bedrock_client=bedrock_client,
#             use_local_tools=use_local_tools,
#         )

#         super().__init__(
#             model="openai.gpt-oss-20b-1:0",
#             system_prompt=self._get_system_prompt(),
#             tools=[self.search_literature, self.analyze_papers],
#         )

#         self.logger = logging.getLogger(f"ResearchOrchestrator-{self.session_id}")
#         self.logger.setLevel(log_level)
#         self.logger.info(
#             f"Research Orchestrator initialized (session: {self.session_id})"
#         )

#     def _get_system_prompt(self) -> str:
#         return (
#             "You are a master research orchestrator. Your goal is to conduct research on a given topic. "
#             "Follow these steps:\n"
#             "1. Use your `search_literature` tool to find relevant academic papers on the user's topic.\n"
#             "2. Once you have a list of papers, use your `analyze_papers` tool to process the top 3 most relevant ones.\n"
#             "3. After the analysis is complete, present a final, comprehensive report to the user that includes the analysis summaries."
#         )

#     @tool
#     async def search_literature(self, query: str) -> Dict[str, Any]:
#         """
#         Searches academic databases for relevant papers on a given topic.
#         :param query: The research topic or query to search for.
#         """
#         self.logger.info(f"Delegating literature search for query: {query}")
#         return await self.searcher_agent.search_literature(query=query)

#     @tool
#     async def analyze_papers(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
#         """
#         Processes a list of papers to extract and synthesize their content.
#         :param papers: A list of paper dictionary objects to be analyzed.
#         """
#         self.logger.info(
#             f"Delegating analysis of {len(papers)} papers to AnalyzerAgent."
#         )
#         return await self.analyzer_agent.analyze_papers(papers=papers)

#     async def process_message(self, message: str, context=None) -> str:
#         self.logger.info(
#             f"Orchestrator received message: '{message}'. Handing off to model-driven workflow."
#         )
#         return await self(message, context=context)


# def create_research_orchestrator(**kwargs) -> ResearchOrchestrator:
#     return ResearchOrchestrator(**kwargs)


orchestrator_prompt = """
You are the Chief Research Orchestrator managing a team of specialist AI agents to conduct comprehensive scientific literature research.

## Your Role

You coordinate five specialist agents to fulfill user research requests:
- PlannerAgent: Strategic research design and decomposition
- SearcherAgent: Literature discovery and curation
- AnalyzerAgent: Technical synthesis and insight extraction
- CritiqueAgent: Quality assurance and validation
- ReporterAgent: Final report generation

## Decision Framework

### Query Classification
SIMPLE QUERY indicators:
- Single focused topic (e.g., "latest CRISPR papers")
- Specific technique or method
- Well-defined scope
- No comparison or multiple perspectives needed

COMPLEX QUERY indicators:
- Multiple aspects or perspectives (e.g., "technical AND ethical")
- Requires comparison between approaches
- Broad topic needing decomposition
- Words like "impact", "implications", "comprehensive review"

### Workflow Selection

FOR SIMPLE QUERIES:
1. Go directly to paper_searcher_tool
2. Pass to paper_analyzer_tool
3. Optional: research_critique_tool if quality uncertain
4. Generate report via report_generator_tool

FOR COMPLEX QUERIES:
1. Start with research_planner_tool
2. Execute plan: for each sub-topic:
   a. Call paper_searcher_tool
   b. Call paper_analyzer_tool
3. Call research_critique_tool on all analyses
4. Handle critique feedback (see below)
5. Call report_generator_tool

## Iteration Management

### Handling Critique Feedback

When CritiqueAgent returns verdict="REVISE":
1. Review required_revisions array
2. For each revision:
   - If action="search_more_papers": Call paper_searcher_tool with specified query
   - If action="re_analyze": Call paper_analyzer_tool with additional focus
3. Increment iteration_count
4. Call research_critique_tool again
5. STOP after 3 iterations even if not approved (prevent infinite loops)

### Handling Clarification Requests

If AnalyzerAgent returns clarification_searches_needed:
1. For each high-importance term:
   a. Call paper_searcher_tool with focused query on that term
   b. Provide clarification papers back to paper_analyzer_tool
2. Continue main workflow

## Communication Guidelines

Always explain to the user what you're doing:
- "I'm engaging the Planner to break down your complex query..."
- "The Searcher is finding relevant papers on [topic]..."
- "The Analyzer is synthesizing findings from 15 papers..."
- "The Critique identified a gap in coverage. Searching for additional papers on [topic]..."

## Error Handling

If a specialist agent fails:
- Transient errors (timeouts, rate limits): Retry once
- No results found: Explain to user, try broader search, or continue with other sub-topics
- Permanent errors: Note the limitation and continue workflow

## Constraints

- Maximum 3 critique-revision cycles per research request
- If time is running short (Lambda timeout approaching), proceed to report with current findings
- Always track state: which sub-topics completed, iteration count, total papers collected

## Output Format

Your final message should contain the complete research report in markdown format.
Include transparent notes about any limitations encountered during research."""


model_id = "openai.gpt-oss-20b-1:0"

model = BedrockModel(model_id)

memory_id = get_ssm_parameter("/app/user_research/agentcore/memory_id")
memory_hooks = AgentCoreMemoryHook(
    memory_id=memory_id, client=memory_client, actor_id=ACTOR_ID, session_id=SESSION_ID
)


@tool
def searcher_agent_tool(query: str) -> str:
    """
    Searches academic databases for relevant papers on a given topic.

    This tool queries multiple sources (arXiv, Semantic Scholar) to find relevant
    academic papers. It returns paper metadata including titles, abstracts, authors,
    and PDF URLs, and automatically initiates processing for selected papers.

    The tool accepts either:
    - Simple string: "CRISPR gene editing applications"
    - Structured JSON with sub-topic information (from planner agent)

    Args:
        query: The research topic or query to search for. Can be a simple topic
               string or a JSON string containing structured sub-topic information
               with description, keywords, and search guidance.

    Returns:
        JSON string containing search results with paper metadata, relevance scores,
        processing status, and search strategy explanation.
    """
    if searcher_agent is None:
        return "❌ Searcher agent not initialized"

    try:
        logger.info(f"🔍 Executing paper search")

        # Try to parse as JSON first (structured sub-topic)
        try:
            sub_topic = json.loads(query)
            formatted_query = format_search_query(sub_topic, include_directives=True)
        except (json.JSONDecodeError, TypeError):
            # It's a simple string query
            formatted_query = format_search_query(query, include_directives=True)

        # Execute the search
        response = searcher_agent(formatted_query)
        return str(response)

    except Exception as e:
        logger.error(f"Error during literature search: {e}")
        return f"❌ Error during literature search: {str(e)}"


@tool
def planner_agent_tool(query: str) -> str:
    """
    Plans the research approach and decomposes complex queries into sub-topics.

    Args:
        query: The complex research question to plan for.

    Returns:
        A structured research plan with sub-topics and search strategies.
    """
    try:
        logger.info(f"Planning research for query: {query}")
        response = planner_agent.structured_output(
            output_model=ResearchPlan, prompt=query
        )
        # Convert to dict for better serialization
        return response.model_dump_json(indent=2)
    except Exception as e:
        logger.error(f"Error during research planning: {e}")
        return f"❌ Error during research planning: {str(e)}"


orchestrator_agent = Agent(
    model=model,
    tools=[searcher_agent_tool, planner_agent_tool],
    system_prompt=orchestrator_prompt,
    hooks=[memory_hooks],
)
