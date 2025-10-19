from datetime import datetime
import json
import logging
from typing import List, Dict, Any
from strands import Agent, tool, ToolContext
from strands.models import BedrockModel

# from backend.agent.utils.utils import (
#     get_ssm_parameter,
#     put_ssm_parameter,
#     enrich_papers_with_s3_paths,
# )
# from backend.agent.utils.agentcore_memory import (
#     AgentCoreMemoryHook,
#     memory_client,
#     ACTOR_ID,
#     SESSION_ID,
#     create_or_get_memory_resource,
# )

from bedrock_agentcore.runtime import (
    BedrockAgentCoreApp,
)

# from memory_reader import MemoryReader
from planner.planner_agent import execute_planning
from searcher.searcher_agent import cleanup, execute_search
from analyzer.analyzer_agent import execute_analysis, run_test_mode
from critique.critique_agent import critique
from reporter.reporter_agent import report

logger = logging.getLogger(__name__)

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
- Call `analyzer_agent_tool` for the one paper, using the s3 paths
- Store the single result
- Do not loop or progress to other topics

### Phase 3: QUALITY ASSURANCE
- Call `critique_agent_tool` with complete research
- Evaluate critique verdict

**IF APPROVED:**
  - Proceed to Phase 4 (Reporting)

**IF REVISE:**
  - Check revision count < MAX_REVISION_CYCLES (2)
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
- "[SEARCH] Analyzing your research question..."
- "[PAPERS] Searching for papers on [topic]..."
- "[ANALYSIS] Analyzing findings from X papers..."
- "[COMPLETE] Quality validation complete..."
- "[REPORT] Generating comprehensive report..."

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


model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
)


# Register all tools with proper decorators
@tool(context=True)
def planner_tool(query: str, tool_context: ToolContext) -> str:
    """Execute the planning phase"""
    try:
        # Store the original query in state
        tool_context.agent.state.set("user_query", query)
        tool_context.agent.state.set("phase", "PLANNING")

        response = execute_planning(query)

        # Store the research plan in state
        tool_context.agent.state.set("research_plan", response)
        tool_context.agent.state.set("current_subtopic_index", 0)

        return response
    except Exception as e:
        logger.error(f"Error in planning phase: {str(e)}")
        raise


@tool(context=True)
def searcher_tool(query: str, tool_context: ToolContext) -> str:
    """Execute the search phase"""
    try:
        tool_context.agent.state.set("phase", "SEARCH")

        # Get current subtopic index
        current_index = tool_context.agent.state.get("current_subtopic_index") or 0

        # Get previously processed paper IDs
        processed_papers = tool_context.agent.state.get("processed_paper_ids") or set()

        response = execute_search(query)

        # Track papers by ID to avoid reprocessing
        if isinstance(response, list):
            # Extract paper IDs based on common response structure
            new_papers = [
                paper
                for paper in response
                if (isinstance(paper, dict) and paper.get("id") not in processed_papers)
            ]

            # Update processed papers set
            processed_papers.update(
                paper.get("id")
                for paper in new_papers
                if isinstance(paper, dict) and "id" in paper
            )
            tool_context.agent.state.set("processed_paper_ids", processed_papers)

            # Store paper metadata by ID for reference
            paper_metadata = tool_context.agent.state.get("paper_metadata") or {}
            for paper in new_papers:
                if isinstance(paper, dict) and "id" in paper:
                    paper_metadata[paper["id"]] = {
                        "title": paper.get("title") or "",
                        "source": paper.get("source") or "",
                        "url": paper.get("url") or "",
                        "subtopic_index": current_index,
                    }
            tool_context.agent.state.set("paper_metadata", paper_metadata)

            # Initialize or update papers by subtopic
            all_papers = tool_context.agent.state.get("all_papers_by_subtopic") or {}
            all_papers[str(current_index)] = new_papers
            tool_context.agent.state.set("all_papers_by_subtopic", all_papers)

            response = new_papers

        return response
    except Exception as e:
        logger.error(f"Error in search phase: {str(e)}")
        raise


@tool(context=True)
def analyzer_tool(paper_uris: List[str], tool_context: ToolContext) -> str:
    """Execute the analysis phase"""
    try:
        tool_context.agent.state.set("phase", "ANALYSIS")

        # Get current subtopic index and revision information
        current_index = tool_context.agent.state.get("current_subtopic_index") or 0
        revision_count = tool_context.agent.state.get("revision_count") or 0

        # Track revision history for this subtopic
        revision_history = tool_context.agent.state.get("revision_history") or {}
        if str(current_index) not in revision_history:
            revision_history[str(current_index)] = []

        # Execute analysis
        response = execute_analysis(paper_uris)

        # Store analysis results and revision history
        analyses = tool_context.agent.state.get("analyses") or {}
        analyses[str(current_index)] = response

        # Add analysis to revision history with metadata
        revision_entry = {
            "analysis": response,
            "timestamp": str(datetime.now()),
            "revision_number": len(revision_history[str(current_index)]) + 1,
            "paper_uris": paper_uris,
            "global_revision_count": revision_count,
        }
        revision_history[str(current_index)].append(revision_entry)

        # Update state
        tool_context.agent.state.set("analyses", analyses)
        tool_context.agent.state.set("revision_history", revision_history)

        # Track paper processing status
        processed_papers = tool_context.agent.state.get("processed_paper_status") or {}
        for uri in paper_uris:
            processed_papers[uri] = {
                "last_analyzed": str(datetime.now()),
                "subtopic_index": current_index,
                "revision_number": revision_entry["revision_number"],
            }
        tool_context.agent.state.set("processed_paper_status", processed_papers)

        return response
    except Exception as e:
        logger.error(f"Error in analysis phase: {str(e)}")
        raise


@tool(context=True)
def critique_tool(analysis_report: str, tool_context: ToolContext) -> str:
    """Execute the critique phase"""
    try:
        tool_context.agent.state.set("phase", "CRITIQUE")

        # Get all necessary state for comprehensive critique
        user_query = tool_context.agent.state.get("user_query") or ""
        research_plan = tool_context.agent.state.get("research_plan") or {}
        analyses = tool_context.agent.state.get("analyses") or {}
        revision_count = tool_context.agent.state.get("revision_count") or 0

        # Execute comprehensive critique across all analyses
        response = critique(
            original_query=user_query,
            research_plan=research_plan,
            analyses=analyses,
            revision_count=revision_count,
        )

        # Parse critique response
        try:
            critique_data = json.loads(response)
            verdict = critique_data.get("verdict", "")

            # Store critique results
            tool_context.agent.state.set("critique_results", critique_data)

            # Handle revision if needed
            if verdict == "REVISE":
                tool_context.agent.state.set("revision_count", revision_count + 1)

                # Store required revisions for each subtopic
                revisions = critique_data.get("required_revisions", [])
                tool_context.agent.state.set("pending_revisions", revisions)

            # If approved, prepare for reporting
            elif verdict == "APPROVED":
                tool_context.agent.state.set("quality_validated", True)
                tool_context.agent.state.set(
                    "overall_quality_score",
                    critique_data.get("overall_quality_score") or 0.0,
                )

        except json.JSONDecodeError:
            logger.error("Failed to parse critique response as JSON")
            raise

        return response
    except Exception as e:
        logger.error(f"Error in critique phase: {str(e)}")
        raise


@tool(context=True)
def reporter_tool(critique_report: str, tool_context: ToolContext) -> str:
    """Execute the reporting phase"""
    try:
        tool_context.agent.state.set("phase", "REPORTING")

        # Get all necessary state for the report
        user_query = tool_context.agent.state.get("user_query") or ""
        research_plan = tool_context.agent.state.get("research_plan") or {}
        analyses = tool_context.agent.state.get("analyses") or {}

        # Generate report using all available state
        response = report(user_query, research_plan, analyses, critique_report)

        # Store the final report
        tool_context.agent.state.set("final_report", response)
        tool_context.agent.state.set("phase", "COMPLETE")

        return response
    except Exception as e:
        logger.error(f"Error in reporting phase: {str(e)}")
        raise


app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload):
    user_query = payload.get("user_query", "No query provided.")

    orchsetrator_agent = Agent(
        model=model,
        system_prompt=ORCHESTRATOR_PROMPT,
        tools=[
            planner_tool,
            searcher_tool,
            analyzer_tool,
            reporter_tool,
            critique_tool,
        ],
    )
    response = orchsetrator_agent(user_query)

    return response


if __name__ == "__main__":
    import sys
    import logging
    import io

    # Set up UTF-8 encoding for output
    if sys.platform.startswith("win"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    # Enable debug logging
    logging.getLogger("strands").setLevel(logging.DEBUG)
    logging.basicConfig(
        format="%(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler()],
    )

    # Test query
    user_query = {"user_query": "Compare YOLO and resnet models"}

    print(f"\n{'=' * 60}", flush=True)
    print("Testing Orchestrator with query:", flush=True)
    print(f"{user_query}", flush=True)
    print(f"{'=' * 60}\n", flush=True)

    try:
        # Execute orchestrator
        response = invoke(user_query)

        # Print results
        print(f"\n{'=' * 60}", flush=True)
        print("RESPONSE:", flush=True)
        print(f"{'=' * 60}", flush=True)

        # Handle Unicode characters safely
        message = response.message
        if isinstance(message, str):
            # Replace Unicode emoji with ASCII alternatives
            message = (
                message.replace("✅", "[OK]")
                .replace("❌", "[X]")
                .replace("⚠️", "[!]")
                .replace("📝", "[*]")
                .encode("ascii", "replace")
                .decode("ascii")
            )

        print(message, flush=True)

        # Print metrics
        print(f"\n{'=' * 60}", flush=True)
        print("METRICS:", flush=True)
        print(f"{'=' * 60}", flush=True)

        metrics_summary = response.metrics.get_summary()
        if isinstance(metrics_summary, str):
            metrics_summary = metrics_summary.encode("ascii", "replace").decode("ascii")
        print(metrics_summary, flush=True)

    except Exception as e:
        print(f"\nError executing orchestrator: {str(e)}", flush=True)
        raise
