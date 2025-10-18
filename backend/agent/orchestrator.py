from datetime import datetime
import logging
from typing import List
import boto3
from strands import Agent, tool
from strands.models import BedrockModel
from strands.agent.state import AgentState
from strands.hooks import (
    AfterInvocationEvent,
    HookProvider,
    HookRegistry,
    MessageAddedEvent,
)

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
from searcher.searcher_agent import execute_search
from analyzer.analyzer_agent import execute_analysis
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
@tool
def planner_tool(query: str) -> str:
    """Execute the planning phase"""
    return execute_planning(query)


@tool
def searcher_tool(query: str) -> str:
    """Execute the search phase"""
    return execute_search(query)


@tool
def analyzer_tool(paper_uris: List[str]) -> str:
    """Execute the analysis phase"""
    return execute_analysis(paper_uris)


@tool
def critique_tool(analysis_report: str) -> str:
    """Execute the critique phase"""
    return critique(analysis_report)


@tool
def reporter_tool(critique_report: str) -> str:
    """Execute the reporting phase"""
    return report(critique_report)


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
    app.run()
