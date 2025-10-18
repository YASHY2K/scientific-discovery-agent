"""
Research Orchestrator - Multi-Agent Research Workflow Coordinator
Coordinates planner, searcher, analyzer, critique, and reporter agents
with AgentCore memory integration for context persistence.
"""

from datetime import datetime
import json
import logging
import requests
from typing import Optional, List, Dict, Any
import boto3
from botocore.exceptions import ClientError
from strands import Agent, tool
from strands.models import BedrockModel
from strands.agent.state import AgentState
from strands.hooks import (
    AfterInvocationEvent,
    HookProvider,
    HookRegistry,
    MessageAddedEvent,
)

from backend.agent.utils.utils import get_ssm_parameter, put_ssm_parameter
from backend.agent.utils.agentcore_memory import (
    AgentCoreMemoryHook,
    memory_client,
    ACTOR_ID,
    SESSION_ID,
    create_or_get_memory_resource,
)
from memory_reader import MemoryReader
from planner.planner_agent import execute_planning
from searcher.searcher_agent import execute_search
from analyzer.analyzer_agent import execute_analysis
from backend.agent.critique.critique_agent import critique
from reporter_agent import report

import json


# ============================================================================
# LOGGING SETUP
# ============================================================================


def setup_logging():
    """Configure logging to output to both file and console"""
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_formatter = logging.Formatter("%(levelname)s | %(name)s | %(message)s")

    # Create logs directory
    import os

    logs_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(logs_dir, exist_ok=True)

    log_path = os.path.join(
        logs_dir,
        f"research_orchestrator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
    )

    # File handler with UTF-8 encoding
    file_handler = None
    try:
        file_handler = logging.FileHandler(
            log_path, mode="w", encoding="utf-8"
        )  # Added encoding
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)
        print(f"Log file: {log_path}")
    except Exception as e:
        print(f"Warning: Could not create log file: {e}")

    # Console handler with UTF-8 encoding
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    # Set console encoding to UTF-8
    if hasattr(console_handler.stream, "reconfigure"):
        console_handler.stream.reconfigure(encoding="utf-8")

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    if file_handler:
        root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Set Strands logger level
    logging.getLogger("strands").setLevel(logging.INFO)


logger = logging.getLogger(__name__)
setup_logging()


# ============================================================================
# CONSTANTS
# ============================================================================

MAX_REVISION_CYCLES = 2
MIN_QUALITY_SCORE = 0.75


# ============================================================================
# ORCHESTRATOR SYSTEM PROMPT
# ============================================================================

ORCHESTRATOR_PROMPT = """You are the Chief Research Orchestrator managing a team of specialist AI agents.

Your role is to coordinate a comprehensive research workflow through multiple phases:

## Agent Team
1. **Planner Agent**: Decomposes complex queries into research sub-topics
2. **Searcher Agent**: Finds relevant academic papers from arXiv and Semantic Scholar
3. **Analyzer Agent**: Performs deep analysis of papers based on search guidance
4. **Critique Agent**: Validates research quality and identifies gaps
5. **Reporter Agent**: Generates comprehensive final reports

## Workflow Phases

### Phase 1: PLANNING
- Receive user research query
- Call `planner_agent_tool` with the query
- Store research plan in state
- Inform user of decomposition results

### Phase 2: SEARCH (TEST MODE)
- Call `searcher_agent_tool` ONCE with the single sub-topic
- Wait for completion of one paper search
- Call `analyzer_agent_tool` for the one paper
- Store the single result
- Do not loop or progress to other topics

### Phase 3: QUALITY ASSURANCE
- Call `critique_agent_tool` with complete research
- Evaluate critique verdict

**IF APPROVED:**
  - Proceed to Phase 4 (Reporting)

**IF REVISE:**
  - Check revision count < MAX_REVISION_CYCLES
  - Execute required revisions based on critique feedback
  - Re-run critique
  - If MAX_REVISION_CYCLES reached, force approve

### Phase 4: REPORTING
- Call `reporter_agent_tool` with all research data
- Present final markdown report to user
- Mark workflow as complete

## State Management

The orchestrator maintains these state variables:
- `user_query`: Original research question
- `research_plan`: Full plan from planner (sub-topics, guidance)
- `current_subtopic_index`: Current position in research loop
- `analyses`: Completed analyses by sub-topic ID
- `all_papers_by_subtopic`: Papers found for each sub-topic
- `revision_count`: Number of revision cycles executed
- `phase`: Current workflow phase
- `critique_results`: Latest critique feedback
- `final_report`: Generated report (when complete)

## Communication Style

Keep the user informed with clear status updates:
- "🔍 Analyzing your research question..."
- "📚 Searching for papers on [topic]..."
- "🔬 Analyzing findings from X papers..."
- "✅ Quality validation complete..."
- "📄 Generating comprehensive report..."

Be concise but informative. Show progress without overwhelming detail.

## Error Handling

If any tool fails:
- Log the error clearly
- Attempt recovery if possible
- Inform user of issues
- Continue workflow if non-critical

## Tool Usage Rules

- Always use tools in the correct phase order
- Wait for tool completion before proceeding
- Validate tool outputs before using them
- Store results in state immediately after tool calls
- Never skip the critique phase
"""


# ============================================================================
# SECRETS MANAGER HELPER
# ============================================================================


def get_api_key(secret_name: str, region_name: str = "us-east-1") -> Optional[str]:
    """
    Retrieves a secret from AWS Secrets Manager.

    Args:
        secret_name: The name of the secret to retrieve
        region_name: The AWS region where the secret is stored

    Returns:
        The secret string if successful, otherwise None
    """
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)

    try:
        response = client.get_secret_value(SecretId=secret_name)
        if "SecretString" in response:
            return response["SecretString"]
    except ClientError as e:
        logger.error(f"Error retrieving secret '{secret_name}': {e}")

    return None


# ============================================================================
# PAPER ID PROCESSING AND S3 ENRICHMENT
# ============================================================================


def process_id(paper_id: str) -> str:
    """
    Convert paper IDs to arXiv IDs for S3 path generation.

    Examples:
        - "arxiv:1910.04751v3" -> "1910.04751v3"
        - "s2:4a12695287ab959..." -> Look up arXiv ID via Semantic Scholar API

    Args:
        paper_id: Paper identifier from search results

    Returns:
        arXiv ID string, or empty string if not found
    """
    parts = paper_id.split(":", 1)

    if len(parts) != 2:
        logger.warning(f"Invalid paper ID format: {paper_id}")
        return ""

    source, identifier = parts

    if source == "arxiv":
        return identifier

    elif source == "s2":
        # Query Semantic Scholar API to get arXiv ID
        url = f"https://api.semanticscholar.org/graph/v1/paper/{identifier}?fields=externalIds"
        headers = {}

        # Add API key if available
        api_key = get_api_key("SEMANTIC_SCHOLAR_API_KEY")
        if api_key:
            headers["x-api-key"] = api_key

        try:
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()

            external_ids = data.get("externalIds", {})
            if "ArXiv" in external_ids:
                arxiv_id = external_ids["ArXiv"]
                logger.info(f"✅ Found arXiv ID for S2 paper: {arxiv_id}")
                return arxiv_id
            else:
                logger.warning(f"⚠️  No arXiv ID found for S2 paper: {identifier}")

        except Exception as e:
            logger.error(f"❌ Error fetching arXiv ID for {identifier}: {e}")

    else:
        logger.warning(f"Unknown paper source: {source}")

    return ""


def enrich_papers_with_s3_paths(papers: List[Dict]) -> List[Dict]:
    """
    Add S3 paths to papers based on their arXiv IDs.

    Args:
        papers: List of paper dictionaries from search results

    Returns:
        Enriched papers with S3 paths added
    """
    enriched_papers = []

    for paper in papers:
        paper_copy = paper.copy()
        paper_id = paper.get("id", "")

        if paper_id:
            arxiv_id = process_id(paper_id)

            if arxiv_id:
                paper_copy["arxiv_id"] = arxiv_id
                paper_copy["s3_text_path"] = (
                    f"s3://ai-agent-hackathon-processed-pdf-files/{arxiv_id}/full_text.txt"
                )
                paper_copy["s3_chunks_path"] = (
                    f"s3://ai-agent-hackathon-processed-pdf-files/{arxiv_id}/chunks.json"
                )
                logger.debug(f"📦 Enriched: {paper_copy['s3_text_path']}")
            else:
                paper_copy["arxiv_id"] = None
                paper_copy["s3_text_path"] = None
                paper_copy["s3_chunks_path"] = None
                logger.warning(
                    f"⚠️  No arXiv ID for: {paper.get('title', 'Unknown')[:50]}"
                )
        else:
            paper_copy["arxiv_id"] = None
            paper_copy["s3_text_path"] = None
            paper_copy["s3_chunks_path"] = None

        enriched_papers.append(paper_copy)

    return enriched_papers


# ============================================================================
# ORCHESTRATOR AGENT CREATION
# ============================================================================


def create_orchestrator():
    """
    Create orchestrator agent with state management and memory hooks.

    Returns:
        Configured Agent instance with state and hooks
    """
    logger.info("🚀 Initializing Research Orchestrator...")

    # Define initial state structure
    initial_state = {
        "user_query": None,
        "research_plan": None,
        "current_subtopic_index": 0,
        "analyses": {},
        "all_papers_by_subtopic": {},
        "revision_count": 0,
        "phase": "init",
        "critique_results": None,
        "final_report": None,
    }

    research_state = AgentState(initial_state=initial_state)

    # Configure model
    model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        temperature=0.3,
    )

    # Setup memory hooks
    hooks = None
    try:
        # Create or retrieve memory resource
        memory_id = create_or_get_memory_resource()

        if memory_id:
            memory_hooks = AgentCoreMemoryHook(
                memory_id=memory_id,
                client=memory_client,
                actor_id=ACTOR_ID,
                session_id=SESSION_ID,
            )
            hooks = [memory_hooks]
            logger.info("✅ AgentCore memory hooks enabled")
        else:
            logger.warning(
                "⚠️  Memory resource creation failed, continuing without memory"
            )

    except Exception as e:
        logger.warning(f"⚠️  Could not load AgentCore memory hooks: {e}")
        logger.info("Continuing without persistent memory...")

    # Create orchestrator agent
    orchestrator = Agent(
        model=model,
        system_prompt=ORCHESTRATOR_PROMPT,
        state=research_state,
        agent_id="research-orchestrator",
        hooks=hooks,
    )

    logger.info("✅ Research Orchestrator initialized successfully")
    return orchestrator


# Global orchestrator instance
orchestrator_agent = create_orchestrator()


# ============================================================================
# AGENT TOOLS
# ============================================================================


@tool
def planner_agent_tool(query: str) -> str:
    """Decompose research query into sub-topics using the planner agent.

    This tool:
    - Validates the input query
    - Calls the Planner Agent to analyze the query
    - Decomposes into focused sub-topics
    - Stores research plan in orchestrator state
    - Updates phase to 'research'

    Args:
        query (str): The research question to analyze

    Returns:
        str: JSON string containing the research plan with sub-topics

    Raises:
        ValueError: If query validation fails
    """
    logger.info("🔍 PLANNER: Starting query validation...")

    try:
        # Input validation
        if not isinstance(query, str):
            raise ValueError(f"Query must be a string, got {type(query)}")

        query = query.strip()
        if not query:
            raise ValueError("Query cannot be empty")

        if len(query) < 10:
            raise ValueError("Query too short - needs to be at least 10 characters")

        if len(query) > 1000:
            raise ValueError("Query too long - maximum 1000 characters allowed")

        # Check for basic question structure
        if not any(
            q in query.lower()
            for q in ["what", "how", "why", "which", "where", "when", "who"]
        ):
            logger.warning(
                "⚠️ PLANNER: Query may not be a well-formed research question"
            )

        logger.info(f"🔍 PLANNER: Processing validated query: {query[:100]}...")

        # Call the planner agent
        plan = execute_planning(query)

        # Try parsing as JSON first
        try:
            plan_dict = json.loads(plan)
            if "plan" not in plan_dict:
                raise ValueError("Invalid plan format: missing 'plan' key")
            plan_data = plan_dict["plan"]
        except json.JSONDecodeError:
            # If JSON parsing fails, try model_dump()
            if not hasattr(plan, "model_dump"):
                raise ValueError(
                    "Plan result must be JSON string or have model_dump() method"
                )
            plan_dict = plan.model_dump()
            plan_data = plan_dict

            # Validate plan structure and contents
        if not isinstance(plan_data, dict):
            raise ValueError("Plan must be a dictionary")

        required_fields = ["sub_topics", "description", "success_criteria"]
        missing_fields = [f for f in required_fields if f not in plan_data]
        if missing_fields:
            raise ValueError(
                f"Invalid plan structure: missing required fields {missing_fields}"
            )

        sub_topics = plan_data.get("sub_topics", [])
        if not isinstance(sub_topics, list):
            raise ValueError("sub_topics must be a list")

        if not sub_topics:
            raise ValueError("Plan must contain at least one sub-topic")

        # Validate each sub-topic structure
        for i, topic in enumerate(sub_topics):
            if not isinstance(topic, dict):
                raise ValueError(f"Sub-topic {i} must be a dictionary")

            topic_required = [
                "id",
                "description",
                "suggested_keywords",
                "search_guidance",
            ]
            missing = [f for f in topic_required if f not in topic]
            if missing:
                raise ValueError(f"Sub-topic {i} missing required fields: {missing}")

            # Validate search guidance structure
            guidance = topic.get("search_guidance", {})
            if not isinstance(guidance, dict):
                raise ValueError(
                    f"Search guidance for sub-topic {i} must be a dictionary"
                )

            guidance_required = ["focus_on", "must_include", "avoid"]
            missing_guidance = [f for f in guidance_required if f not in guidance]
            if missing_guidance:
                raise ValueError(
                    f"Search guidance for sub-topic {i} missing: {missing_guidance}"
                )

        # Prepare state updates after validation
        state_updates = {
            "user_query": query,
            "research_plan": plan_data,
            "current_subtopic_index": 0,
            "phase": "research",
        }

        # Update state atomically
        for key, value in state_updates.items():
            orchestrator_agent.state.set(key, value)  # Log success
        num_subtopics = len(plan_data.get("sub_topics", []))
        logger.info(f"✅ PLANNER: Plan created with {num_subtopics} sub-topics")
        logger.info("✅ PLANNER: State updated successfully")

        # Return consistent JSON response
        return json.dumps(
            {
                "status": "success",
                "plan": plan_data,
                "num_subtopics": num_subtopics,
                "state_updates": state_updates,
            },
            indent=2,
        )

    except Exception as e:
        logger.error(f"❌ PLANNER ERROR: {e}", exc_info=True)
        return json.dumps(
            {
                "status": "error",
                "error": str(e),
                "message": "Failed to create research plan",
            },
            indent=2,
        )


@tool
def searcher_agent_tool(subtopic_description: str) -> str:
    """
    Search for academic papers related to a research sub-topic.

    This tool:
    - Validates current research state
    - Calls the Searcher Agent to find papers
    - Enriches results with S3 paths for processed papers
    - Stores results in orchestrator state
    - Returns standardized JSON response

    Args:
        subtopic_description: Description of the sub-topic to search

    Returns:
        JSON string with search results and S3 paths
    """
    logger.info("🔍 SEARCHER: Starting paper search process...")

    try:
        # Validate state and get required data
        state = orchestrator_agent.state.get()
        if not state:
            raise ValueError("Agent state not initialized")

        plan = state.get("research_plan")
        if not plan:
            raise ValueError("No research plan found in state")

        current_index = state.get("current_subtopic_index", 0)
        sub_topics = plan.get("sub_topics", [])

        if not sub_topics:
            raise ValueError("Research plan contains no sub-topics")

        if current_index >= len(sub_topics):
            raise ValueError(
                f"Invalid subtopic index: {current_index} >= {len(sub_topics)}"
            )

        # Get current subtopic details
        current_subtopic = sub_topics[current_index]
        subtopic_id = current_subtopic.get("id")
        if not subtopic_id:
            raise ValueError("Current subtopic missing ID")

        logger.info(f"🔍 SEARCHER: Processing subtopic '{subtopic_id}'")

        # Prepare search input with validation
        search_input = {
            "id": subtopic_id,
            "description": subtopic_description.strip(),
            "suggested_keywords": current_subtopic.get("suggested_keywords", []),
            "search_guidance": current_subtopic.get("search_guidance", {}),
        }

        # Validate search input
        if not search_input["description"]:
            raise ValueError("Empty subtopic description provided")

        logger.info(f"🔍 SEARCHER: Executing search for subtopic '{subtopic_id}'")
        search_result = execute_search(search_input, verbose=False)

        # Parse search results with proper error handling
        try:
            if isinstance(search_result, str):
                search_data = json.loads(search_result)
            elif hasattr(search_result, "model_dump"):
                search_data = search_result.model_dump()
            else:
                search_data = search_result

            if not isinstance(search_data, dict):
                raise ValueError("Search result is not a valid dictionary")

            # Process and validate papers
            papers = search_data.get("selected_papers", [])
            if not papers:
                logger.warning(f"⚠️ No papers found for subtopic '{subtopic_id}'")
                return json.dumps(
                    {
                        "status": "warning",
                        "subtopic_id": subtopic_id,
                        "message": "Search completed but no papers were found",
                    },
                    indent=2,
                )

            # Enrich papers with S3 paths
            enriched_papers = enrich_papers_with_s3_paths(papers)
            valid_papers = [p for p in enriched_papers if p.get("s3_text_path")]

            # Update state with new papers
            all_papers = state.get("all_papers_by_subtopic", {})
            all_papers[subtopic_id] = enriched_papers
            orchestrator_agent.state.set("all_papers_by_subtopic", all_papers)

            logger.info(
                f"✅ SEARCHER: Found {len(enriched_papers)} papers ({len(valid_papers)} with S3 paths)"
            )

            # Return standardized success response
            return json.dumps(
                {
                    "status": "success",
                    "subtopic_id": subtopic_id,
                    "metadata": {
                        "total_papers": len(enriched_papers),
                        "papers_with_s3": len(valid_papers),
                        "keywords": search_input["suggested_keywords"],
                    },
                    "papers": enriched_papers,
                    "state_updates": {
                        "all_papers_by_subtopic": {subtopic_id: enriched_papers}
                    },
                },
                indent=2,
            )

        except json.JSONDecodeError as e:
            logger.error(f"❌ SEARCHER: Failed to parse search results: {e}")
            raise ValueError(f"Invalid search result format: {e}")

    except ValueError as e:
        # Handle known validation errors
        logger.error(f"❌ SEARCHER: Validation error: {e}")
        return json.dumps(
            {"status": "error", "error_type": "validation", "message": str(e)}, indent=2
        )

    except Exception as e:
        # Handle unexpected errors
        logger.error(f"❌ SEARCHER: Unexpected error: {e}", exc_info=True)
        return json.dumps(
            {
                "status": "error",
                "error_type": "unexpected",
                "message": f"Search operation failed: {str(e)}",
            },
            indent=2,
        )


@tool
def analyzer_agent_tool() -> str:
    """
    Analyze papers for the current sub-topic.

    This tool:
    - Validates analysis prerequisites and state
    - Retrieves papers from state
    - Validates paper content and S3 paths
    - Applies search guidance for focused analysis
    - Calls Analyzer Agent with validated S3 URIs
    - Stores analysis results with quality metrics
    - Advances to next sub-topic if successful

    Returns:
        JSON string with analysis results and validation metadata

    Raises:
        ValueError: If state validation fails
        RuntimeError: If analysis execution fails
    """
    logger.info("🔬 ANALYZER: Starting analysis process...")

    try:
        # Validate state initialization
        state = orchestrator_agent.state.get()
        if not state:
            raise ValueError("Agent state not initialized")

        # Validate required state components
        required_state = [
            "research_plan",
            "current_subtopic_index",
            "all_papers_by_subtopic",
        ]
        missing_state = [f for f in required_state if state.get(f) is None]
        if missing_state:
            raise ValueError(f"Missing required state components: {missing_state}")

        plan = state["research_plan"]
        current_index = state["current_subtopic_index"]
        all_papers = state["all_papers_by_subtopic"]

        # Validate research plan structure
        if not isinstance(plan, dict) or "sub_topics" not in plan:
            raise ValueError("Invalid research plan structure")

        if not plan or current_index >= len(plan.get("sub_topics", [])):
            logger.error("❌ ANALYZER: Invalid research state")
            return json.dumps({"status": "error", "error": "Invalid research state"})

        current_subtopic = plan["sub_topics"][current_index]
        subtopic_id = current_subtopic["id"]
        papers = all_papers.get(subtopic_id, [])

        if not papers:
            logger.warning(f"⚠️  ANALYZER: No papers to analyze for '{subtopic_id}'")
            orchestrator_agent.state.set("current_subtopic_index", current_index + 1)
            return json.dumps(
                {
                    "status": "skipped",
                    "subtopic_id": subtopic_id,
                    "message": "No papers available for analysis",
                }
            )

        # Extract valid S3 URIs
        paper_uris = [
            paper.get("s3_text_path") for paper in papers if paper.get("s3_text_path")
        ]

        if not paper_uris:
            logger.warning(f"⚠️  ANALYZER: No valid S3 paths for '{subtopic_id}'")
            orchestrator_agent.state.set("current_subtopic_index", current_index + 1)
            return json.dumps(
                {
                    "status": "skipped",
                    "subtopic_id": subtopic_id,
                    "message": "No valid S3 paths available",
                }
            )

        logger.info(
            f"🔬 ANALYZER: Analyzing {len(paper_uris)} papers for '{subtopic_id}'..."
        )

        # Build analysis context
        search_guidance = current_subtopic.get("search_guidance", {})
        context = f"""
Sub-Topic: {subtopic_id}
Description: {current_subtopic.get("description", "N/A")}
Success Criteria: {current_subtopic.get("success_criteria", "N/A")}

Search Guidance (Focus your analysis on these criteria):
- Focus on: {search_guidance.get("focus_on", "N/A")}
- Must include: {search_guidance.get("must_include", "N/A")}
- Avoid: {search_guidance.get("avoid", "N/A")}

INSTRUCTIONS:
1. Read each paper's content from the S3 path
2. Extract findings relevant to the search guidance
3. Map findings to specific criteria
4. Identify contradictions and research gaps
5. Provide confidence metrics
"""

        # Execute analysis
        analysis_result = execute_analysis(
            paper_uris=paper_uris, context=context, verbose=False
        )

        # Parse and store results
        try:
            analysis_data = json.loads(analysis_result)
        except json.JSONDecodeError:
            logger.warning("⚠️  ANALYZER: Could not parse analysis as JSON")
            analysis_data = {"raw_analysis": analysis_result, "parse_error": True}

        # Store in state
        analyses = state.get("analyses", {})
        analyses[subtopic_id] = analysis_data
        orchestrator_agent.state.set("analyses", analyses)

        # Move to next sub-topic
        orchestrator_agent.state.set("current_subtopic_index", current_index + 1)

        logger.info(f"✅ ANALYZER: Analysis complete for '{subtopic_id}'")

        return json.dumps(
            {
                "status": "success",
                "subtopic_id": subtopic_id,
                "papers_analyzed": len(paper_uris),
                "analysis": analysis_data,
            },
            indent=2,
        )

    except Exception as e:
        logger.error(f"❌ ANALYZER ERROR: {e}")
        return json.dumps({"status": "error", "error": str(e)})


@tool
def critique_agent_tool() -> str:
    """
    Evaluate research quality and completeness.

    This tool:
    - Calls Critique Agent with all analyses
    - Evaluates completeness, accuracy, balance, depth
    - Returns verdict (APPROVED or REVISE)
    - Provides actionable feedback

    Returns:
        JSON string with critique verdict and feedback
    """
    try:
        state = orchestrator_agent.state.get()
        user_query = state.get("user_query")
        plan = state.get("research_plan")
        analyses = state.get("analyses", {})
        revision_count = state.get("revision_count", 0)

        if not user_query or not plan or not analyses:
            logger.error("❌ CRITIQUE: Incomplete research state")
            return json.dumps(
                {"status": "error", "error": "Cannot critique incomplete research"}
            )

        logger.info(
            f"✅ CRITIQUE: Evaluating research (revision {revision_count}/{MAX_REVISION_CYCLES})..."
        )

        # Execute critique
        critique_result = critique(
            original_query=user_query,
            research_plan=plan,
            analyses=analyses,
            revision_count=revision_count,
        )

        # Parse results
        try:
            critique_data = json.loads(critique_result)
        except json.JSONDecodeError:
            logger.warning("⚠️  CRITIQUE: Could not parse critique as JSON")
            critique_data = {
                "raw_critique": critique_result,
                "parse_error": True,
                "verdict": "APPROVED",  # Default to approved if parsing fails
            }

        # Store critique results
        orchestrator_agent.state.set("critique_results", critique_data)
        orchestrator_agent.state.set("phase", "critique_complete")

        verdict = critique_data.get("verdict", "APPROVED")
        quality_score = critique_data.get("overall_quality_score", 0.0)

        logger.info(f"✅ CRITIQUE: Verdict = {verdict}, Quality = {quality_score:.2f}")

        return json.dumps(
            {
                "status": "success",
                "verdict": verdict,
                "quality_score": quality_score,
                "critique": critique_data,
            },
            indent=2,
        )

    except Exception as e:
        logger.error(f"❌ CRITIQUE ERROR: {e}")
        return json.dumps(
            {
                "status": "error",
                "error": str(e),
                "verdict": "APPROVED",  # Fail open
            }
        )


@tool
def reporter_agent_tool() -> str:
    """
    Generate comprehensive research report.

    This tool:
    - Calls Reporter Agent with all research data
    - Generates markdown formatted report
    - Stores final report in state

    Returns:
        JSON string with report generation status
    """
    try:
        state = orchestrator_agent.state.get()
        user_query = state.get("user_query")
        plan = state.get("research_plan")
        analyses = state.get("analyses", {})
        critique_feedback = state.get("critique_results")

        if not user_query or not plan or not analyses:
            logger.error("❌ REPORTER: Incomplete research data")
            return json.dumps(
                {
                    "status": "error",
                    "error": "Cannot generate report with incomplete research",
                }
            )

        logger.info("📄 REPORTER: Generating comprehensive report...")

        # Generate report
        report_text = report(
            original_query=user_query,
            research_plan=plan,
            analyses=analyses,
            critique_feedback=critique_feedback,
            save_to_file=False,
        )

        # Store report
        orchestrator_agent.state.set("final_report", report_text)
        orchestrator_agent.state.set("phase", "complete")

        logger.info("✅ REPORTER: Report generation complete")

        return json.dumps(
            {
                "status": "success",
                "message": "Research report generated successfully",
                "report_length": len(report_text),
                "report": report_text,
            },
            indent=2,
        )

    except Exception as e:
        logger.error(f"❌ REPORTER ERROR: {e}")
        return json.dumps({"status": "error", "error": str(e)})


# ============================================================================
# HIGH-LEVEL WORKFLOW FUNCTIONS
# ============================================================================


def run_research_workflow(user_query: str, max_retries: int = 3) -> str:
    """
    Execute complete research workflow with error handling.

    Args:
        user_query: The research question
        max_retries: Maximum retry attempts for failed steps

    Returns:
        Final research report as markdown string
    """
    logger.info("=" * 80)
    logger.info(f"🚀 Starting Research Workflow")
    logger.info(f"Query: {user_query}")
    logger.info("=" * 80)

    # Reset state
    orchestrator_agent.state.set("user_query", None)
    orchestrator_agent.state.set("research_plan", None)
    orchestrator_agent.state.set("current_subtopic_index", 0)
    orchestrator_agent.state.set("analyses", {})
    orchestrator_agent.state.set("all_papers_by_subtopic", {})
    orchestrator_agent.state.set("revision_count", 0)
    orchestrator_agent.state.set("phase", "planning")  # Start with planning phase
    orchestrator_agent.state.set("critique_results", None)
    orchestrator_agent.state.set("final_report", None)

    try:
        # Phase 1: Planning
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 1: PLANNING")
        logger.info("=" * 80)

        response = orchestrator_agent(
            f"Please create a research plan for: {user_query}"
        )
        logger.info(f"Planning response: {str(response)[:200]}...")

        # Parse the planner tool's response
        try:
            planner_response = json.loads(str(response))
            if (
                isinstance(planner_response, dict)
                and planner_response.get("status") == "success"
                and isinstance(planner_response.get("plan"), dict)
            ):
                # Store the plan in state
                orchestrator_agent.state.set("research_plan", planner_response["plan"])
                logger.info("✅ Planning phase completed successfully")
            else:
                logger.error(
                    f"❌ Unexpected planner response format: {planner_response}"
                )
                raise ValueError("Invalid planner response format")
        except json.JSONDecodeError as e:
            logger.error(f"❌ Could not parse planner response: {e}")
            raise ValueError("Failed to parse planner response")

        # Verify state was updated
        state = orchestrator_agent.state.get()
        plan = state.get("research_plan")

        # Double-check state update
        if not state.get("user_query"):
            orchestrator_agent.state.set("user_query", user_query)

        if not plan:
            logger.error("❌ Planning phase failed - checking what was returned...")
            logger.error(f"State after planning: {json.dumps(state, indent=2)}")
            raise ValueError(
                "Planning phase failed - no plan created. Check logs for details."
            )

        # Phase 2: Research Loop
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 2: RESEARCH")
        logger.info("=" * 80)

        # Set phase to research
        orchestrator_agent.state.set("phase", "research")

        num_subtopics = len(plan.get("sub_topics", []))
        for i in range(num_subtopics):
            subtopic = plan["sub_topics"][i]
            logger.info(
                f"\n--- Sub-topic {i + 1}/{num_subtopics}: {subtopic['id']} ---"
            )

            # Search and analyze
            response = orchestrator_agent(
                f"Search and analyze papers for sub-topic: {subtopic['description']}"
            )
            logger.info(f"Research response: {str(response)[:200]}...")

        # Phase 3: Quality Assurance
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 3: QUALITY ASSURANCE")
        logger.info("=" * 80)

        # Set phase to critique
        orchestrator_agent.state.set("phase", "critique")

        response = orchestrator_agent(
            "Please evaluate the research quality using the critique agent"
        )
        logger.info(f"Critique response: {str(response)[:200]}...")

        # Check if revisions needed
        state = orchestrator_agent.state.get()
        critique_results = state.get("critique_results", {})
        verdict = critique_results.get("verdict", "APPROVED")

        if verdict == "REVISE" and state.get("revision_count", 0) < MAX_REVISION_CYCLES:
            logger.info("⚠️  Revisions required, implementing feedback...")
            # TODO: Implement revision logic based on critique feedback
            # For now, we'll proceed to reporting

        # Phase 4: Reporting
        logger.info("\n" + "=" * 80)
        logger.info("PHASE 4: REPORTING")
        logger.info("=" * 80)

        # Set phase to reporting
        orchestrator_agent.state.set("phase", "reporting")

        response = orchestrator_agent("Please generate the final research report")
        logger.info(f"Report response: {str(response)[:200]}...")

        # Retrieve final report
        state = orchestrator_agent.state.get()
        final_report = state.get("final_report")

        if not final_report:
            raise ValueError("Reporting phase failed - no report generated")

        logger.info("\n" + "=" * 80)
        logger.info("✅ WORKFLOW COMPLETE")
        logger.info("=" * 80)

        return final_report

    except Exception as e:
        logger.error(f"\n❌ WORKFLOW ERROR: {e}")
        logger.error("Attempting to generate partial report...")

        # Try to generate report with whatever data we have
        try:
            state = orchestrator_agent.state.get()
            if state.get("analyses"):
                return report(
                    original_query=user_query,
                    research_plan=state.get("research_plan", {}),
                    analyses=state.get("analyses", {}),
                    critique_feedback=None,
                    save_to_file=False,
                )
        except Exception as report_error:
            logger.error(f"Failed to generate partial report: {report_error}")

        return f"# Research Workflow Error\n\nThe research workflow encountered an error: {str(e)}\n\nPlease try again or contact support."


def run_research_workflow_interactive(user_query: str) -> str:
    """
    Execute research workflow with interactive orchestrator calls.
    This allows the orchestrator to manage its own workflow naturally.

    Args:
        user_query: The research question

    Returns:
        Final research report as markdown string
    """
    logger.info("=" * 80)
    logger.info(f"🚀 Starting Interactive Research Workflow")
    logger.info(f"Query: {user_query}")
    logger.info("=" * 80)

    # Reset state
    orchestrator_agent.state.set("user_query", None)
    orchestrator_agent.state.set("research_plan", None)
    orchestrator_agent.state.set("current_subtopic_index", 0)
    orchestrator_agent.state.set("analyses", {})
    orchestrator_agent.state.set("all_papers_by_subtopic", {})
    orchestrator_agent.state.set("revision_count", 0)
    orchestrator_agent.state.set("phase", "init")
    orchestrator_agent.state.set("critique_results", None)
    orchestrator_agent.state.set("final_report", None)

    try:
        # Single call to orchestrator - let it manage the workflow
        initial_prompt = f"""Execute a complete research workflow for the following query:

"{user_query}"

Follow all phases in order:
1. Planning - decompose the query
2. Research - search and analyze for each sub-topic
3. Quality Assurance - critique the research
4. Reporting - generate final report

Use the appropriate tools at each phase and keep me informed of progress."""

        response = orchestrator_agent(initial_prompt)

        # Check if workflow completed
        state = orchestrator_agent.state.get()
        final_report = state.get("final_report")

        if final_report:
            logger.info("✅ Interactive workflow completed successfully")
            return final_report
        else:
            logger.warning("⚠️  Workflow incomplete, generating status report...")
            return f"# Research Status\n\nWorkflow is in progress.\n\nCurrent phase: {state.get('phase')}\n\nOrchestrator response:\n{response}"

    except Exception as e:
        logger.error(f"❌ Interactive workflow error: {e}")
        return f"# Research Workflow Error\n\nError: {str(e)}"


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def get_workflow_status() -> Dict[str, Any]:
    """
    Get current workflow status.

    Returns:
        Dictionary with current state information
    """
    state = orchestrator_agent.state.get()

    plan = state.get("research_plan") or {}
    analyses = state.get("analyses") or {}

    return {
        "phase": state.get("phase"),
        "user_query": state.get("user_query"),
        "num_subtopics": len(plan.get("sub_topics", [])),
        "current_subtopic_index": state.get("current_subtopic_index"),
        "completed_analyses": len(analyses),
        "revision_count": state.get("revision_count"),
        "has_critique": state.get("critique_results") is not None,
        "has_report": state.get("final_report") is not None,
    }


def reset_workflow():
    """Reset the workflow state to initial conditions."""
    logger.info("🔄 Resetting workflow state...")

    orchestrator_agent.state.set("user_query", None)
    orchestrator_agent.state.set("research_plan", None)
    orchestrator_agent.state.set("current_subtopic_index", 0)
    orchestrator_agent.state.set("analyses", {})
    orchestrator_agent.state.set("all_papers_by_subtopic", {})
    orchestrator_agent.state.set("revision_count", 0)
    orchestrator_agent.state.set("phase", "init")
    orchestrator_agent.state.set("critique_results", None)
    orchestrator_agent.state.set("final_report", None)

    logger.info("✅ Workflow state reset complete")


def save_workflow_state(filename: str = None):
    """
    Save current workflow state to JSON file.

    Args:
        filename: Optional filename (default: auto-generated)
    """
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"workflow_state_{timestamp}.json"

    state = orchestrator_agent.state.get()

    try:
        with open(filename, "w") as f:
            json.dump(state, f, indent=2)
        logger.info(f"💾 Workflow state saved to {filename}")
        return filename
    except Exception as e:
        logger.error(f"❌ Failed to save workflow state: {e}")
        return None


# ============================================================================
# MAIN EXECUTION AND TESTING
# ============================================================================


def main():
    """Main execution function for testing."""
    print("\n" + "=" * 80)
    print("🔬 RESEARCH ORCHESTRATOR - TEST MODE")
    print("=" * 80)

    # Test query
    test_query = (
        "Compare reinforcement learning and supervised learning for robotics control"
    )

    print(f"\n📝 Test Query: {test_query}")
    print("\n" + "-" * 80)

    try:
        # Option 1: Structured workflow (more controlled)
        print("\n🚀 Running structured workflow...\n")
        result = run_research_workflow(test_query)

        # Option 2: Interactive workflow (more autonomous)
        # print("\n🚀 Running interactive workflow...\n")
        # result = run_research_workflow_interactive(test_query)

        print("\n" + "=" * 80)
        print("📄 FINAL REPORT")
        print("=" * 80)
        print(result)
        print("=" * 80)

        # Save report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"research_report_{timestamp}.md"
        with open(report_filename, "w") as f:
            f.write(result)
        print(f"\n💾 Report saved to: {report_filename}")

        # Show workflow status
        status = get_workflow_status()
        print("\n📊 Workflow Status:")
        for key, value in status.items():
            print(f"  {key}: {value}")

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        print("Saving current workflow state...")
        save_workflow_state()

    except Exception as e:
        logger.error(f"❌ Fatal error in main: {e}")
        print(f"\n❌ ERROR: {e}")
        print("\nSaving workflow state for debugging...")
        save_workflow_state()
        raise


def test_individual_tools():
    """Test each tool individually."""
    print("\n" + "=" * 80)
    print("🔧 TESTING INDIVIDUAL TOOLS")
    print("=" * 80)

    test_query = "Compare reinforcement learning and supervised learning for robotics"

    try:
        # Test planner
        print("\n1️⃣  Testing Planner Tool...")
        plan_result = planner_agent_tool(test_query)
        print(f"Result: {plan_result[:500]}...")

        # Test searcher (requires plan to be set)
        print("\n2️⃣  Testing Searcher Tool...")
        state = orchestrator_agent.state.get()
        if state.get("research_plan"):
            searcher_result = searcher_agent_tool(
                "reinforcement learning for robot control"
            )
            print(f"Result: {searcher_result[:500]}...")

        # Test analyzer (requires papers to be found)
        print("\n3️⃣  Testing Analyzer Tool...")
        if state.get("all_papers_by_subtopic"):
            analyzer_result = analyzer_agent_tool()
            print(f"Result: {analyzer_result[:500]}...")

        # Test critique (requires analyses)
        print("\n4️⃣  Testing Critique Tool...")
        if state.get("analyses"):
            critique_result = critique_agent_tool()
            print(f"Result: {critique_result[:500]}...")

        # Test reporter (requires all data)
        print("\n5️⃣  Testing Reporter Tool...")
        if state.get("analyses"):
            reporter_result = reporter_agent_tool()
            print(f"Result: {reporter_result[:500]}...")

        print("\n✅ Individual tool testing complete")

    except Exception as e:
        logger.error(f"❌ Tool testing error: {e}")
        print(f"\n❌ ERROR: {e}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            # Run full workflow test
            main()
        elif sys.argv[1] == "tools":
            # Test individual tools
            test_individual_tools()
        elif sys.argv[1] == "status":
            # Show current status
            status = get_workflow_status()
            print("\n📊 Current Workflow Status:")
            print(json.dumps(status, indent=2))
        elif sys.argv[1] == "reset":
            # Reset workflow
            reset_workflow()
            print("✅ Workflow reset complete")
        else:
            # Run workflow with custom query
            custom_query = " ".join(sys.argv[1:])
            result = run_research_workflow(custom_query)
            print(result)
    else:
        print("""
Usage:
  python research_orchestrator.py test           # Run test workflow
  python research_orchestrator.py tools          # Test individual tools
  python research_orchestrator.py status         # Show workflow status
  python research_orchestrator.py reset          # Reset workflow state
  python research_orchestrator.py <query>        # Run custom query
        """)
        main()  # Run default test
