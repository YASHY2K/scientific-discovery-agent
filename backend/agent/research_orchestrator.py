import logging
from typing import Optional, List, Dict, Any
import boto3
from strands import Agent, tool
from strands.models import BedrockModel
from strands.agent.state import AgentState

from utils import get_ssm_parameter
from agent.agentcore_memory import (
    AgentCoreMemoryHook,
    memory_client,
    ACTOR_ID,
    SESSION_ID,
)
from planner_agent import planner_agent, ResearchPlan
from searcher.searcher_agent import searcher_agent, format_search_query
from analyzer.analyzer_agent import analyzer_agent

import json

logging.getLogger("strands").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s", handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

orchestrator_prompt = """You are the Chief Research Orchestrator managing a team of specialist AI agents.

Your role is to coordinate a comprehensive research workflow:
1. Planner Agent: Decomposes complex queries into sub-topics
2. Searcher Agent: Finds relevant academic papers
3. Analyzer Agent: Performs focused analysis based on search guidance
4. Critique Agent: Validates quality and identifies gaps
5. Reporter Agent: Generates final comprehensive report

## Workflow Phases

### Phase 1: Planning
- Receive user research query
- Call planner_agent_tool to decompose into sub-topics
- Store plan in state
- Report decomposition to user

### Phase 2: Research Loop
For each sub-topic in the plan:
  1. Call searcher_agent_tool with sub-topic description
  2. Call analyzer_agent_tool to analyze papers with search guidance
  3. Store results in state
  4. Move to next sub-topic

### Phase 3: Quality Assurance
- Call critique_agent_tool with all analyses
- Check verdict

IF verdict = APPROVED:
  - Proceed to Phase 4

IF verdict = REVISE:
  - Check revision_count < MAX_REVISION_CYCLES
  - IF yes: Execute required revisions (search for gaps, re-analyze)
  - IF no: Force approve

### Phase 4: Report Generation
- Call reporter_agent_tool with complete research context
- Deliver final markdown report

## State Management

Maintain orchestrator state:
- user_query: Original research question
- research_plan: Decomposed sub-topics from planner
- current_subtopic_index: Track progress through sub-topics
- analyses: Store each sub-topic's analysis (by subtopic_id)
- all_papers_by_subtopic: Store papers found (by subtopic_id)
- revision_count: Prevent infinite loops
- phase: Current workflow phase (planning, research, critique, reporting, complete)

## Communication

Keep user informed at each major step:
- "Decomposing your research question..."
- "Searching for papers on [sub-topic]..."
- "Analyzing findings..."
- "Validating research quality..."
- "Generating final report..."
"""


def create_orchestrator():
    """Create orchestrator agent with state management."""

    # Define initial state structure
    initial_state = {
        "user_query": None,
        "research_plan": None,
        "current_subtopic_index": 0,
        "analyses": {},  # {subtopic_id: analysis_output}
        "all_papers_by_subtopic": {},  # {subtopic_id: [papers_list]}
        "revision_count": 0,
        "phase": "init",  # init, planning, research, critique, reporting, complete
    }

    research_state = AgentState(initial_state=initial_state)
    model = BedrockModel(model_id="us.anthropic.claude-3-5-sonnet-20241022-v1:0")

    try:
        memory_id = get_ssm_parameter("/app/user_research/agentcore/memory_id")
        memory_hooks = AgentCoreMemoryHook(
            memory_id=memory_id,
            client=memory_client,
            actor_id=ACTOR_ID,
            session_id=SESSION_ID,
        )
        hooks = [memory_hooks]
    except Exception as e:
        logger.warning(f"Could not load AgentCore memory hooks: {e}")
        hooks = None

    orchestrator = Agent(
        model=model,
        system_prompt=orchestrator_prompt,
        state=research_state,
        agent_id="research-orchestrator",
        hooks=hooks,
    )

    return orchestrator


orchestrator_agent = create_orchestrator()


@tool
def planner_agent_tool(query: str) -> str:
    """
    Decompose a complex research query into manageable sub-topics.

    This tool calls the Planner Agent to:
    - Analyze query complexity
    - Determine research approach
    - Decompose into sub-topics with search guidance

    Args:
        query: The research question to decompose

    Returns:
        JSON string containing the research plan with sub-topics and search guidance
    """
    try:
        logger.info(f"Planner: Decomposing query: {query}")

        # Call planner agent
        plan = planner_agent.structured_output(output_model=ResearchPlan, prompt=query)

        plan_dict = plan.model_dump()

        # Update orchestrator state
        state = orchestrator_agent.state.get()
        state["user_query"] = query
        state["research_plan"] = plan_dict
        state["current_subtopic_index"] = 0
        state["phase"] = "research"
        orchestrator_agent.state.set("user_query", query)
        orchestrator_agent.state.set("research_plan", plan_dict)
        orchestrator_agent.state.set("phase", "research")

        logger.info(
            f"Planner: Research plan created with {len(plan_dict['sub_topics'])} sub-topics"
        )

        return json.dumps(plan_dict, indent=2)

    except Exception as e:
        logger.error(f"Planner error: {e}")
        return json.dumps({"error": str(e), "status": "failed"})


def extract_arxiv_id_from_url(pdf_url: str) -> Optional[str]:
    """Extract arXiv ID from PDF URL."""
    if not pdf_url or "arxiv.org/pdf/" not in pdf_url:
        return None
    try:
        filename = pdf_url.split("/")[-1]
        arxiv_id = filename.replace(".pdf", "")
        return arxiv_id
    except Exception as e:
        logger.warning(f"Failed to extract arXiv ID from URL: {e}")
        return None


def enrich_papers_with_s3_paths(papers: List[Dict]) -> List[Dict]:
    """Add S3 paths to papers based on their arXiv IDs."""
    enriched_papers = []

    for paper in papers:
        paper_copy = paper.copy()
        pdf_url = paper.get("pdf_url", "")
        arxiv_id = extract_arxiv_id_from_url(pdf_url)

        if arxiv_id:
            paper_copy["arxiv_id"] = arxiv_id
            paper_copy["s3_text_path"] = (
                f"s3://ai-agent-hackathon-processed-pdf-files/{arxiv_id}/full_text.txt"
            )
            paper_copy["s3_chunks_path"] = (
                f"s3://ai-agent-hackathon-processed-pdf-files/{arxiv_id}/chunks.json"
            )
            logger.info(f"Enriched paper with S3 path: {paper_copy['s3_text_path']}")
        else:
            paper_copy["arxiv_id"] = None
            paper_copy["s3_text_path"] = None
            paper_copy["s3_chunks_path"] = None
            logger.warning(f"Could not extract arXiv ID for: {paper.get('title')}")

        enriched_papers.append(paper_copy)

    return enriched_papers


@tool
def searcher_agent_tool(subtopic_description: str) -> str:
    """
    Search for papers related to a specific research sub-topic.

    This tool:
    - Calls the Searcher Agent to find papers
    - Enriches results with S3 paths for processed papers
    - Stores results in orchestrator state

    Args:
        subtopic_description: Description of the sub-topic to search for

    Returns:
        JSON string with search results including S3 paths
    """
    try:
        state = orchestrator_agent.state.get()
        plan = state.get("research_plan")
        current_index = state.get("current_subtopic_index", 0)

        if not plan or current_index >= len(plan["sub_topics"]):
            logger.error("Invalid research state for searcher")
            return json.dumps({"error": "Invalid research state", "status": "failed"})

        current_subtopic = plan["sub_topics"][current_index]
        subtopic_id = current_subtopic["id"]

        logger.info(f"Searcher: Searching for '{subtopic_id}'")

        # Format query with search guidance
        search_input = {
            "description": subtopic_description,
            "keywords": current_subtopic.get("suggested_keywords", []),
            "search_guidance": current_subtopic.get("search_guidance", {}),
        }

        formatted_query = format_search_query(search_input, include_directives=True)

        # Call searcher agent
        search_result = searcher_agent(formatted_query)

        # Parse and enrich with S3 paths
        try:
            search_data = json.loads(str(search_result))

            if "selected_papers" in search_data:
                enriched_papers = enrich_papers_with_s3_paths(
                    search_data["selected_papers"]
                )
                search_data["selected_papers"] = enriched_papers

                # Store papers in state
                all_papers = state.get("all_papers_by_subtopic", {})
                all_papers[subtopic_id] = enriched_papers
                orchestrator_agent.state.set("all_papers_by_subtopic", all_papers)

                logger.info(
                    f"Searcher: Found {len(enriched_papers)} papers for '{subtopic_id}'"
                )

            return json.dumps(search_data, indent=2)

        except json.JSONDecodeError:
            logger.warning("Searcher: Could not parse output as JSON")
            return str(search_result)

    except Exception as e:
        logger.error(f"Searcher error: {e}")
        return json.dumps({"error": str(e), "status": "failed"})


@tool
def analyzer_agent_tool() -> str:
    """
    Analyze papers for the current sub-topic using search guidance.

    This tool:
    - Reads papers from state
    - Applies search guidance for focused analysis
    - Calls Analyzer Agent with context
    - Stores analysis in state

    Returns:
        JSON string with focused analysis
    """
    try:
        state = orchestrator_agent.state.get()
        plan = state.get("research_plan")
        # NOTE: The index is not incremented here, so we get the current one
        current_index = state.get("current_subtopic_index", 0)
        all_papers = state.get("all_papers_by_subtopic", {})

        if not plan or current_index >= len(plan["sub_topics"]):
            logger.error("Invalid research state for analyzer")
            return json.dumps({"error": "Invalid research state", "status": "failed"})

        current_subtopic = plan["sub_topics"][current_index]
        subtopic_id = current_subtopic["id"]
        papers = all_papers.get(subtopic_id, [])

        if not papers:
            logger.warning(f"Analyzer: No papers found for '{subtopic_id}' to analyze.")
            # Move to the next sub-topic even if no papers were found to avoid getting stuck
            orchestrator_agent.state.set("current_subtopic_index", current_index + 1)
            return json.dumps(
                {"error": f"No papers found for {subtopic_id}", "status": "skipped"}
            )

        logger.info(f"Analyzer: Analyzing {len(papers)} papers for '{subtopic_id}'")

        # Create analysis prompt with search guidance and paper content
        analysis_prompt = f"""Analyze the following papers for this research sub-topic.

Sub-Topic ID: {subtopic_id}
Description: {current_subtopic["description"]}
Success Criteria: {current_subtopic.get("success_criteria", "N/A")}

Search Guidance (IMPORTANT - focus your analysis on these criteria):
- Focus on: {current_subtopic.get("search_guidance", {}).get("focus_on", "N/A")}
- Must include: {current_subtopic.get("search_guidance", {}).get("must_include", "N/A")}
- Avoid: {current_subtopic.get("search_guidance", {}).get("avoid", "N/A")}

Papers to analyze:
{json.dumps(papers, indent=2)}

INSTRUCTIONS:
1. For each paper, read its content from the S3 path (s3_text_path field).
2. Extract ONLY findings relevant to the search guidance criteria.
3. Map findings to specific criteria (focus_on fields).
4. Identify contradictions within this sub-topic.
5. Find research gaps specific to this sub-topic.
6. Note any unfamiliar terms requiring clarification.
7. Return structured JSON analysis.

Return the analysis in the specified structured format.
"""

        # Call analyzer agent
        analysis = analyzer_agent(analysis_prompt)

        # Parse and store analysis
        try:
            analysis_data = json.loads(str(analysis))
        except json.JSONDecodeError:
            logger.warning(
                "Analyzer: Could not parse output as JSON, storing as raw text."
            )
            analysis_data = {"raw_analysis": str(analysis), "parse_error": True}

        # Store in state
        analyses = state.get("analyses", {})
        analyses[subtopic_id] = analysis_data
        orchestrator_agent.state.set("analyses", analyses)

        # Move to next sub-topic for the next iteration of the loop
        orchestrator_agent.state.set("current_subtopic_index", current_index + 1)

        logger.info(f"Analyzer: Analysis complete for '{subtopic_id}'")

        return json.dumps(analysis_data, indent=2)

    except Exception as e:
        logger.error(f"Analyzer error: {e}")
        return json.dumps({"error": str(e), "status": "failed"})


def run_research_workflow(user_query: str) -> str:
    """
    Execute complete research workflow for a user query.

    This is the main entry point that:
    1. Plans the research
    2. Executes search and analysis for each sub-topic
    3. Validates quality
    4. Generates final report

    Args:
        user_query: The research question

    Returns:
        Markdown string with final research report
    """
    logger.info(f"Starting research workflow: {user_query}")

    # Reset state for new workflow
    orchestrator_agent.state.set("user_query", None)
    orchestrator_agent.state.set("research_plan", None)
    orchestrator_agent.state.set("current_subtopic_index", 0)
    orchestrator_agent.state.set("analyses", {})
    orchestrator_agent.state.set("all_papers_by_subtopic", {})
    orchestrator_agent.state.set("revision_count", 0)
    orchestrator_agent.state.set("phase", "init")

    # Phase 1: Planning
    logger.info("Phase 1: Planning")
    orchestrator_agent(f"Please plan the research for: {user_query}")

    # Phase 2: Research loop
    logger.info("Phase 2: Research")
    state = orchestrator_agent.state.get()
    plan = state.get("research_plan")

    if plan:
        for i, subtopic in enumerate(plan["sub_topics"]):
            logger.info(
                f"Processing sub-topic {i + 1}/{len(plan['sub_topics'])}: {subtopic['id']}"
            )
            orchestrator_agent(
                f"Search and analyze papers for: {subtopic['description']}"
            )

    # Phase 3: Critique (placeholder)
    logger.info("Phase 3: Quality Assurance")
    orchestrator_agent("Validate the research quality")

    # Phase 4: Report
    logger.info("Phase 4: Reporting")
    result = orchestrator_agent("Generate the final research report")

    logger.info("Research workflow complete")
    return str(result)


# ============================================================================
# MODULE-LEVEL EXECUTION
# ============================================================================

if __name__ == "__main__":
    # Example usage
    sample_query = "Impact of transformer models on time-series forecasting"
    report = run_research_workflow(sample_query)
    print(report)
