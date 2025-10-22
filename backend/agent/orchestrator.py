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
# from reporter.reporter_agent import write_report_section_tool, finalize_report_tool

logger = logging.getLogger(__name__)

ORCHESTRATOR_PROMPT = """You are the Chief Research Orchestrator managing a team of specialist AI agents.

Your role is to coordinate a comprehensive research workflow through multiple phases:

## Agent Team
1. **Planner Agent**: Decomposes complex queries into research sub-topics
2. **Searcher Agent**: Finds relevant academic papers from arXiv and Semantic Scholar
3. **Analyzer Agent**: Performs deep analysis of papers based on search guidance
4. **Critique Agent**: Validates research quality and identifies gaps
5. **Reporter Agent**: A set of tools ('write_report_section_tool', 'finalize_report_tool') used to write the report section by section.


## Workflow Phases

### Phase 1: PLANNING
- Receive user research query
- Call `planner_tool` with the query
- Store research plan in state
- Inform user of decomposition results

### Phase 2: SEARCH (TEST MODE)
- Call `searcher_tool` ONCE with the single sub-topic
- Wait for completion of one paper search
- Call `analyzer_tool` for the one paper, using the s3 paths
- Store the single result
- Do not loop or progress to other topics

### Phase 3: QUALITY ASSURANCE
- Call `critique_tool` with complete research
- Evaluate critique verdict

**IF APPROVED:**
  - Proceed to Phase 4 (Reporting)

**IF REVISE:**
  - Check revision count < MAX_REVISION_CYCLES (2)
  - Execute required revisions based on critique feedback
  - Re-run critique
  - If MAX_REVISION_CYCLES reached, force approve

### Phase 4: REPORTING (TEST MODE - Chunked Strategy)
-   Initialize `generated_sections` in state.
-   Call `write_report_section_tool` with `section_name='Executive Summary'`.
-   Inform user: "[REPORT] Writing Executive Summary..."
-   Call `write_report_section_tool` with `section_name='Conclusion'`.
-   Inform user: "[REPORT] Writing Conclusion..."
-   Inform user: "[REPORT] Assembling final report..."
-   Call `finalize_report_tool` to combine all sections.
-   Present the final markdown report from `finalize_report_tool` to the user.
-   Mark workflow as complete.

## State Management
The orchestrator maintains these state variables:
-   `user_query`: Original research question
-   `research_plan`: Full plan from planner (sub-topics, guidance)
-   `current_subtopic_index`: Current position in the research loop (for `research_plan.sub_topics`)
-   `analyses`: A dictionary mapping sub-topic IDs to their completed analysis JSON.
-   `all_papers_by_subtopic`: A dictionary mapping sub-topic IDs to the list of papers found.
-   `revision_count`: Number of revision cycles executed
-   `phase`: Current workflow phase
-   `critique_results`: Latest critique feedback
-   `generated_sections`: A dictionary mapping section names to their markdown content.
-   `final_report`: Generated report (when complete)

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


REPORTER_BASE_PROMPT = """You are a Technical Report Writer specializing in academic research synthesis.
Your role is to write ONE specific section of a larger report based on the data provided.
You MUST follow all instructions for the specific section you are given.
CRITICAL: All output MUST use ASCII characters only.

## IMPORTANT: Handling Incomplete Data
- If the analysis contains errors or incomplete data, work with what you have.
- Focus on extracting maximum value from successful analyses.
- Do not apologize for missing data.

## General Writing Guidelines
- **Tone**: Professional, academic, and accessible. Assume an intelligent (but not expert) reader.
- **Evidence**: Use the `quantitative_results` and `key_quotes` from the JSON data extensively. Cite specific metrics.
- **Format**: Return ONLY the markdown for your assigned section. Do NOT include a section header (e.g., "## Executive Summary"), as this will be added later.
"""

# This dictionary holds the specific instructions for each section.
REPORTER_PROMPTS = {
    "Executive Summary": REPORTER_BASE_PROMPT
    + """
## Your Current Task: Write the 'Executive Summary'
- Aim for 5-6 paragraphs. This is the most important section for busy readers.
- **Paragraph 1**: Broad context - why this topic matters.
- **Paragraph 2**: What was investigated (the query) and how (the methodology).
- **Paragraph 3**: Key finding 1, with supporting evidence/metrics.
- **Paragraph 4**: Key finding 2, with supporting evidence/metrics.
- **Paragraph 5**: Practical implications & high-level recommendations.
- **Paragraph 6**: Future outlook / Conclusion.
- **Output**: Start writing the summary directly (no header).
""",
    "Introduction": REPORTER_BASE_PROMPT
    + """
## Your Current Task: Write the 'Introduction'
- Aim for 4-5 paragraphs.
- **Paragraph 1**: Restate the original query in formal academic terms and provide background.
- **Paragraph 2**: Explain why this question is important (practical impact, research gaps).
- **Paragraph 3**: Describe the methodology used (e.g., "A systematic review was conducted... papers were sourced from...").
- **Paragraph 4**: Define the scope of this report and acknowledge limitations upfront.
- **Output**: Start writing the introduction directly (no header).
""",
    "Main Findings": REPORTER_BASE_PROMPT
    + """
## Your Current Task: Write the 'Main Findings'
- This is the most detailed section.
- For EACH sub-topic in the `research_plan.sub_topics`, create a sub-section (e.g., "### [Sub-topic Name]").
- For EACH paper in the `analyses` for that sub-topic:
  1.  **[Paper Title]** by [Authors], [Year]
  2.  - **Core Contribution**: [1-2 sentences]
  3.  - **Methodology**: [Detailed summary, including dataset/sample size if provided by Analyzer]
  4.  - **Key Findings**: (List 2-3 findings, each supported by metrics, stats, or direct quotes from the data)
  5.  - **Significance**: [Why this matters]
  6.  - **Limitations**: [What the paper doesn't cover]
- After listing the papers for a sub-topic, write a 2-3 paragraph **Synthesis** comparing/contrasting them.
- **Output**: Start writing the findings directly (e.g., "### [Sub-topic Name]").
""",
    "Cross-Study Synthesis": REPORTER_BASE_PROMPT
    + """
## Your Current Task: Write the 'Cross-Study Synthesis'
- This is a CRITICAL section. Aim for 5-6 paragraphs minimum. Go beyond just listing themes.
- **Common Themes**: What patterns emerge across ALL sub-topics? (with examples)
- **Contradictions**: Where do findings clash? Hypothesize *why* (e.g., "Paper A and B conflict; this is likely because Paper A used a synthetic dataset...").
- **Methodological Comparison**: Directly compare the *methods* used. Which papers were more robust? What evaluation metrics were common?
- **Evolution of Thinking**: How has the field progressed based on these papers?
- **Practical Implications**: What does this all mean for real-world applications?
- **Output**: Start writing the synthesis directly (no header).
""",
    "Research Gaps": REPORTER_BASE_PROMPT
    + """
## Your Current Task: Write the 'Research Gaps and Future Directions'
- Aim for 3-4 detailed paragraphs.
- **Current Limitations**: What's still unknown based on the analyses? Why does it matter?
- **Emerging Questions**: What new questions arose from this research?
- **Methodological Needs**: What new approaches or data are needed?
- **Priority Ranking**: Which gaps are most important to address first?
- **Output**: Start writing the research gaps directly (no header).
""",
    "Conclusion": REPORTER_BASE_PROMPT
    + """
## Your Current Task: Write the 'Conclusion'
- **Summary Bullet Points**: (8-12 bullets, 1-2 sentences each with specific insights)
- **For Practitioners** (dedicated paragraph): Actionable recommendations. What to do Monday morning.
- **For Researchers** (dedicated paragraph): Future research directions. Open problems worth investigating.
- **Output**: Start writing the conclusion directly (no header).
""",
}

# ============================================================================
# AGENT INITIALIZATION
# ============================================================================

# Define the model globally so our tools can access it
# Note: Using Sonnet 3.5 for strong writing.
# You can change this to match your orchestrator's model if needed.
model = BedrockModel(
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    temperature=0.5,
)
logger.info("Reporter model initialized")


# ============================================================================
# MODULAR TOOLS (To be imported by Orchestrator)
# ============================================================================


@tool(context=True)
def write_report_section_tool(section_name: str, tool_context: ToolContext) -> str:
    """
    Writes a single, specific section of the final research report.
    Valid section_name values are: 'Executive Summary', 'Introduction',
    'Main Findings', 'Cross-Study Synthesis', 'Research Gaps', 'Conclusion'.
    """
    try:
        tool_context.agent.state.set("phase", f"REPORTING: {section_name}")
        logger.info(f"Writing report section: {section_name}")

        # 1. Get the specific prompt for this section
        section_system_prompt = REPORTER_PROMPTS.get(section_name)
        if not section_system_prompt:
            raise ValueError(f"No prompt found for section: {section_name}")

        # 2. Get all the data the reporter needs from state
        user_query = tool_context.agent.state.get("user_query") or ""
        research_plan = tool_context.agent.state.get("research_plan") or {}
        analyses = tool_context.agent.state.get("analyses") or {}
        critique_results = tool_context.agent.state.get("critique_results") or {}

        # 3. Create a temporary, "stateless" agent with this specific prompt
        section_agent = Agent(model=model, system_prompt=section_system_prompt)

        # 4. Create the user prompt, containing only the data
        section_data_prompt = f"""
        Here is the data you must use to write your section:
        
        - Original Query: {user_query}
        - Research Plan: {json.dumps(research_plan, indent=2)}
        - Analyses: {json.dumps(analyses, indent=2)}
        - Critique: {json.dumps(critique_results, indent=2)}
        
        Begin writing your assigned section. Remember, do NOT output a header.
        """

        # 5. Call the agent. This call is small and efficient.
        response = section_agent(section_data_prompt)

        # Extract the text content from the message
        section_content = ""
        for block in response.message["content"]:
            if block["type"] == "text":
                section_content += block.text

        # 6. Save this section's content into state
        generated_sections = tool_context.agent.state.get("generated_sections") or {}
        generated_sections[section_name] = section_content
        tool_context.agent.state.set("generated_sections", generated_sections)

        logger.info(f"Successfully generated section: {section_name}")
        return f"Successfully generated section: {section_name}"

    except Exception as e:
        logger.error(f"Error in reporting section {section_name}: {str(e)}")
        raise


@tool(context=True)
def finalize_report_tool(tool_context: ToolContext) -> str:
    """
    Assembles all generated report sections into the final, complete markdown document.
    This should be the very last tool called.
    """
    try:
        tool_context.agent.state.set("phase", "FINALIZING")
        logger.info("Finalizing full report...")

        generated_sections = tool_context.agent.state.get("generated_sections") or {}

        # Define the order of the report
        section_order = [
            "Executive Summary",
            "Introduction",
            "Main Findings",
            "Cross-Study Synthesis",
            "Research Gaps",
            "Conclusion",
        ]

        final_report_parts = []

        # Add a title
        user_query = tool_context.agent.state.get("user_query") or "Research Report"
        final_report_parts.append(f"# Research Report: {user_query}\n")

        for section_name in section_order:
            section_content = generated_sections.get(section_name)

            # Add section title
            final_report_parts.append(f"\n## {section_name}\n")

            if section_content:
                final_report_parts.append(section_content)
            else:
                final_report_parts.append("*(This section was not generated)*")

        final_report = "\n".join(final_report_parts)

        # Save to state and return the final string
        tool_context.agent.state.set("final_report", final_report)
        tool_context.agent.state.set("phase", "COMPLETE")

        logger.info("Final report assembled.")
        return final_report

    except Exception as e:
        logger.error(f"Error in finalize_report_tool: {str(e)}")
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
            # reporter_tool,
            write_report_section_tool,
            finalize_report_tool,
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
