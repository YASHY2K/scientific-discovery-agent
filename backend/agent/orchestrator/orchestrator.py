import logging

# Configure logging settings
logging.basicConfig(
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler()]
)

logging.getLogger("strands.models").setLevel(logging.WARNING)  # Reduce model initialization noise
logging.getLogger("strands.tools.registry").setLevel(logging.WARNING)  # Reduce tool registration noise
logging.getLogger("strands.tools.mcp").setLevel(logging.INFO)  # Keep important MCP messages

# Initialize this module's logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Standard library imports
from typing import List

# Third-party imports
from strands import Agent, tool
from strands.models import BedrockModel

# Configure logging
logging.getLogger("strands.models").setLevel(logging.WARNING)  # Reduce model initialization noise
logging.getLogger("strands.tools.registry").setLevel(logging.WARNING)  # Reduce tool registration noise
logging.getLogger("strands.tools.mcp").setLevel(logging.INFO)  # Keep important MCP messages

# Set up clear logging format
logging.basicConfig(
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# from memory_reader import MemoryReader
from backend.agent.planner.planner_agent import execute_planning
from backend.agent.searcher.searcher_agent import execute_search
from backend.agent.analyzer.analyzer_agent import execute_analysis
from backend.agent.critique.critique_agent import critique
from backend.agent.reporter.reporter_agent import report


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

while True:
    try:
        user_input = input("You: ").strip()
        if not user_input:
            print("Please tell me how I can help you, or type 'exit' to quit")
            continue
        if user_input.lower() in ["exit", "quit", "bye", "goodbye"]:
            print()
            print("=========================================================")
            print("Thank you for using Personal Assistant!")
            print("Have a productive day ahead!")
            print("Come back anytime you need help!")
            print("=========================================================")
            break

        print("PersonalBot: ", end="")
        response = orchsetrator_agent(user_input)
        print("\n")

    except KeyboardInterrupt:
        print("\n")
        print("=========================================================")
        print("Personal Assistant interrupted!")
        print("See you next time!")
        print("=========================================================")
        break
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        print("Please try again or type 'exit' to quit")
        print()
