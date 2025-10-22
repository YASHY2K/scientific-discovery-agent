"""
Searcher Agent - Scientific Literature Search
Following Strands "Agents as Tools" pattern with pragmatic directive prompting.
This agent specializes in searching academic databases and curating relevant papers.
"""

import logging
import json

# AWS Strands and MCP imports
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from strands.types.exceptions import MCPClientInitializationError
from mcp.client.streamable_http import streamablehttp_client

from .searcher_models import SearchResult
from utils.searcher_helper import (
    enrich_papers_with_s3_paths,
    get_ssm_parameters,
    update_ssm_parameter,
    _is_unauthorized_error,
    get_token,
)

# Enable debug logs
logging.getLogger("strands").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s", handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


# ============================================================================
# AGENT SYSTEM PROMPT
# ============================================================================

SEARCHER_SYSTEM_PROMPT = """You are a Scientific Literature Search Agent. Your mission is to execute a multi-step research workflow using the tools provided.

IMPORTANT: All output MUST use ASCII characters only. Do not use emojis, special characters, or unicode symbols.

## Your Workflow
You MUST follow these steps in order. DO NOT skip any steps.

### Step 1: Search Phase
- First, you MUST call the `Arxiv___search_arxiv` tool to find recent preprints.
- Second, you MUST call the `SemanticScholar___search_semantic_scholar` tool for peer-reviewed papers.
- Use relevant keywords from the user's request. Be adaptive and try different queries if the first search yields poor results.

### Step 2: Selection & Processing Phase (CRITICAL)
- From the combined search results, select the **top 1 to 3 most relevant papers**.
- For **each** of these selected papers, you MUST call the `PaperProcessing___paper_processing` tool one time with its `pdf_url`.
- This step is mandatory and must be completed before generating the final output.

### Step 3: Output Phase
- After you have initiated processing for the selected papers, generate a single, valid JSON object that summarizes the entire operation.
- The `papers_processed` field in the JSON MUST accurately reflect the number of times you called the `PaperProcessing___paper_processing` tool.

## Tool Specifications

1. **Arxiv___search_arxiv**
   - Input: `{"body": {"query": "your search terms", "limit": 5}}`

2. **SemanticScholar___search_semantic_scholar**
   - Input: `{"body": {"query": "your search terms", "action": "search_paper"}}`

3. **PaperProcessing___paper_processing**
   - Input: `{"body": {"pdf_url": "URL to the paper PDF"}}`
   - Note: This tool returns immediately. You will not get data back from it.

## Output Format
Your final output MUST be a single, valid JSON object matching this structure exactly:

```json
{
  "sub_topic_id": "from input or 'general_search'",
  "search_iterations": 2,
  "total_papers_found": 10,
  "selected_papers": [
    {
      "id": "arxiv:2401.12345 or s2:paper_id",
      "title": "Paper Title",
      "authors": ["Author A", "Author B"],
      "abstract": "Full abstract...",
      "source": "arxiv or semantic_scholar",
      "published_date": "2024-01-15",
      "pdf_url": "[https://arxiv.org/pdf/2401.12345.pdf](https://arxiv.org/pdf/2401.12345.pdf) or [https://www.semanticscholar.org/paper/](https://www.semanticscholar.org/paper/)<rest url>",
      "relevance_score": "High",
      "selection_reason": "Directly addresses the core research question.",
      "processing_initiated": true
    }
  ],
  "papers_processed": 5,
  "search_strategy": [
    "Searched arXiv with 'reinforcement learning robot control'.",
    "Searched Semantic Scholar with 'RL vs SL for robotics'.",
    "Selected 5 papers based on relevance and recency.",
    "Initiated processing for the 5 selected papers."
  ],
  "papers_excluded": "Excluded 20 papers that were out of scope.",
  "quality_assessment": "High confidence in the relevance of the selected papers.",
  "recommendations": "Further analysis should focus on the results from the processed papers."
}
```

## Final Validation

Before you finish, you MUST double-check:
- Is the final output a single, valid JSON object?
- Did you call both search tools?
- Did you call the PaperProcessing___paper_processing tool for each of the top papers?
- Does the papers_processed number in your JSON match the number of calls you made to the processing tool?

## Reasoning Guidelines
- Keep internal reasoning concise
- Don't narrate every decision step-by-step
- Focus on final output quality, not process explanation
- Use reasoning only for complex filtering decisions

Failure to follow these steps will result in an incorrect response.
"""

# ============================================================================
# AGENT INITIALIZATION
# ============================================================================


def initialize_searcher_agent():
    """
    Initialize the searcher agent with MCP tools.
    This function handles all the setup including SSM config, token refresh, and MCP client.
    """
    logger.info("(Initializing) Initializing Searcher Agent...")

    # Fetch configuration from SSM
    app_config = get_ssm_parameters()

    # Validate URLs
    gateway_url = app_config.get("AGENTCORE_GATEWAY_URL")
    cognito_url = app_config.get("COGNITO_DISCOVERY_URL")

    if not gateway_url or not gateway_url.startswith(("http://", "https://")):
        raise ValueError(f"Invalid AGENTCORE_GATEWAY_URL: '{gateway_url}'")
    if not cognito_url or not cognito_url.startswith(("http://", "https://")):
        raise ValueError(f"Invalid COGNITO_DISCOVERY_URL: '{cognito_url}'")

    # Configure model
    model_id = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
    model = BedrockModel(model_id=model_id, temperature=0.3)
    gateway_auth_token = app_config["ACCESS_TOKEN"]

    # Initialize MCP Client with retry logic
    max_retries = 2
    mcp_client = None

    for attempt in range(max_retries):
        logger.info(
            f"(Connection) Connecting MCP Client (Attempt {attempt + 1}/{max_retries})..."
        )

        mcp_client = MCPClient(
            lambda: streamablehttp_client(
                gateway_url,
                headers={"Authorization": f"Bearer {gateway_auth_token}"},
            )
        )

        try:
            mcp_client.start()
            logger.info("(Success) MCP Client connected successfully")
            break

        except MCPClientInitializationError as e:
            logger.error(
                f"(Error) MCP client initialization failed on attempt {attempt + 1}"
            )

            if _is_unauthorized_error(e):
                logger.info("Reason: 401 Unauthorized. Refreshing token...")

                if attempt < max_retries - 1:
                    token_response = get_token(
                        client_id=app_config["AC_USER_ID"],
                        client_secret=app_config["AC_USER_SECRET"],
                        scope_string=app_config["AC_USER_SCOPE"],
                        url=cognito_url,
                    )

                    if "access_token" in token_response:
                        gateway_auth_token = token_response["access_token"]
                        update_ssm_parameter("ACCESS_TOKEN", gateway_auth_token)
                        continue

                raise e
            else:
                raise e
    else:
        raise RuntimeError("Failed to initialize MCP client after all retries")

    # List and log available tools
    tools = mcp_client.list_tools_sync()
    logger.info(f"(Success) Loaded {len(tools)} tools:")
    for tool_obj in tools:
        logger.info(f"   - {tool_obj.tool_name}")

    # Create the agent
    agent = Agent(model=model, system_prompt=SEARCHER_SYSTEM_PROMPT, tools=tools)

    logger.info("(Success) Searcher Agent initialized successfully")
    return agent, mcp_client


# Initialize agent and MCP client at module level
searcher_agent = None
mcp_client_instance = None

try:
    searcher_agent, mcp_client_instance = initialize_searcher_agent()
except Exception as e:
    logger.error(f"(Error) Failed to initialize searcher agent: {e}")
    searcher_agent = None
    mcp_client_instance = None


# ============================================================================
# QUERY FORMATTING HELPER
# ============================================================================


def format_search_query(
    query_input: str | dict, include_directives: bool = True
) -> str:
    """
    Format the search query with optional directive reinforcement.

    Args:
        query_input: Either a simple string query or a structured sub-topic dict
        include_directives: If True, adds explicit step-by-step directives to the query.
                          This helps ensure the agent follows the complete workflow,
                          especially important for MCP tool chains.

    Returns:
        Formatted query string ready for the agent
    """
    # Handle structured sub-topic data
    if isinstance(query_input, dict):
        sub_topic_json = json.dumps(query_input, indent=2)
        base_query = f"Execute a literature search for the following research sub-topic:\n{sub_topic_json}"
    else:
        base_query = f"Execute a literature search for: {query_input}"

    # Add directive reinforcement if requested (recommended for reliability)
    if include_directives:
        directives = """

WORKFLOW REMINDER:
1. Call Arxiv___search_arxiv tool to search arXiv preprints
2. Call SemanticScholar___search_semantic_scholar tool to search peer-reviewed papers
3. Select the top 1-2 most relevant papers from combined results
4. For EACH selected paper, call PaperProcessing___paper_processing with its pdf_url
5. Return results in the specified JSON format with accurate papers_processed count

Execute this workflow now, starting with the arXiv search."""
        return base_query + directives

    return base_query


# ============================================================================
# DIRECT EXECUTION HELPER (for testing/standalone use)
# ============================================================================


def execute_search(query_input: str | dict, verbose: bool = True) -> str:
    """
    Execute a search directly using the searcher agent.

    Args:
        query_input: Either a string query or structured sub-topic dict
        verbose: If True, prints progress information

    Returns:
        Agent response as string
    """
    if searcher_agent is None:
        error_msg = "(Error) Cannot execute - agent not initialized"
        if verbose:
            print(error_msg)
        return error_msg

    try:
        # Format the query with directives
        formatted_query = format_search_query(query_input, include_directives=True)

        # Execute the search
        response = searcher_agent(formatted_query)

        structured_response = searcher_agent.structured_output(
            output_model=SearchResult,
            prompt="Extract structured data from response",
        )
        final_response = structured_response.model_dump()
        print(type(final_response), final_response)

        final_response["selected_papers"] = enrich_papers_with_s3_paths(
            final_response["selected_papers"]
        )

        if verbose:
            print("\n(Response) Structured Response:")
            try:
                # Use json.dumps with ensure_ascii=False to handle Unicode characters
                print(json.dumps(final_response, indent=2, ensure_ascii=False))
            except Exception as print_error:
                logger.warning(
                    f"Could not print response with special characters: {print_error}"
                )
                # Fallback: print with ASCII encoding
                print(json.dumps(final_response, indent=2, ensure_ascii=True))
            print()

        return final_response

    except Exception as e:
        error_msg = f"(Error) Error: {str(e)}"
        if verbose:
            print(error_msg)
        logger.error(f"Search execution failed: {e}", exc_info=True)
        return error_msg


# ============================================================================
# STANDALONE TESTING AND CLI
# ============================================================================


def run_test_mode():
    """Run the searcher agent in test mode with predefined query."""
    if searcher_agent is None:
        print("(Error) Cannot start - agent initialization failed")
        return

    print("=" * 80)
    print("(Test Mode) Searcher Agent - Test Mode")
    print("=" * 80)
    print()

    # Test with structured sub-topic
    test_sub_topic = {
        "id": "cv_semantic_segmentation_survey",
        "description": "Conduct a comprehensive survey of deep learning architectures and methodologies used for semantic segmentation in computer vision.",
        "suggested_keywords": [
            "semantic segmentation deep learning",
            "fully convolutional networks",
            "vision transformers segmentation",
            "U-Net architecture",
            "DeepLab family",
        ],
        "search_guidance": {
            "must_include": "seminal papers on architectures like FCN, U-Net, DeepLab, and recent Transformer-based models",
            "focus_on": "architectural innovations, loss functions, performance metrics on benchmark datasets",
            "avoid": "studies focused exclusively on traditional, non-deep-learning image processing techniques",
        },
        "priority": 1,
        "success_criteria": "Synthesize findings from at least 15-20 key papers to provide a holistic overview",
    }

    print(f"(Info) Testing with sub-topic: {test_sub_topic['id']}")
    print()

    # Execute the search
    execute_search(test_sub_topic, verbose=True)


def cleanup():
    """Clean up MCP client connection."""
    if mcp_client_instance:
        logger.info("(Connection) Shutting down MCP Client...")
        try:
            mcp_client_instance.stop(None, None, None)
            logger.info("(Success) MCP Client shut down gracefully")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    import sys
    import io

    # Force UTF-8 encoding for stdout to handle special characters
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )

    try:
        # Check command line arguments
        if len(sys.argv) > 1:
            if sys.argv[1] == "test":
                run_test_mode()
            else:
                print("Usage: python searcher_agent.py [test]")
        else:
            print("Usage: python searcher_agent.py [test]")

    except KeyboardInterrupt:
        print("\n\n(Info) Interrupted by user")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"\n(Error) FATAL ERROR: {e}")
        import sys

        sys.exit(1)

    finally:
        cleanup()
        print("\nGoodbye!")
