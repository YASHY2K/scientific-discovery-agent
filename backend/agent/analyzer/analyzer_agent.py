"""
Analyzer Agent - Scientific Paper Analysis
Following Strands "Agents as Tools" pattern with pragmatic directive prompting.
This agent specializes in analyzing processed papers from S3 and extracting key insights.
"""

import logging
import json
import boto3
from botocore.exceptions import ClientError
from typing import Dict, Any, Optional

# AWS Strands imports
from strands import Agent, tool
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from strands.types.exceptions import MCPClientInitializationError
from mcp.client.streamable_http import streamablehttp_client
import httpx
import requests

# Enable debug logs
logging.getLogger("strands").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s", handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

# S3 client will be initialized after role assumption
s3_client = None

# ============================================================================
# SSM PARAMETER STORE CONFIGURATION
# ============================================================================

SSM_PARAMETERS_MAP = {
    "S3_ACCESS_ROLE_ARN": "/scientific-agent/config/s3-access-role-arn",
}

# ============================================================================
# AGENT SYSTEM PROMPT
# ============================================================================

ANALYZER_SYSTEM_PROMPT = """You are a Scientific Paper Analysis Agent. Your mission is to analyze processed research papers and extract key insights, methodologies, findings, and contributions.

## Your Workflow
You MUST follow these steps in order:

### Step 1: Document Retrieval
- Use the `download_s3_document` tool to retrieve the full text of papers from S3
- The S3 URI format is: `s3://bucket-name/prefix/full_text.txt`
- You can retrieve multiple papers if needed for comparative analysis

### Step 2: Content Analysis
- Carefully read and analyze the full text of each paper
- Extract key information including:
  * Research objectives and questions
  * Methodologies and experimental design
  * Main findings and results
  * Novel contributions and innovations
  * Limitations and future work
  * Citations and related work

### Step 3: Synthesis
- Synthesize findings across multiple papers if applicable
- Identify common themes, contradictions, and research gaps
- Assess the quality and rigor of the research

### Step 4: Output Generation
- Generate a structured JSON output with your analysis
- Include specific quotes and evidence from the papers
- Provide clear, actionable insights

## Tool Specifications

1. **download_s3_document**
   - Input: `{"s3_uri": "s3://bucket-name/prefix/full_text.txt"}`
   - Returns: The full text content of the document
   - Use this tool for each paper you need to analyze

## Output Format
Your final output MUST be a single, valid JSON object matching this structure:

```json
{
  "analysis_id": "unique_identifier",
  "papers_analyzed": [
    {
      "s3_uri": "s3://bucket/prefix/full_text.txt",
      "title": "Extracted or inferred title",
      "key_findings": [
        "Finding 1 with supporting evidence",
        "Finding 2 with supporting evidence"
      ],
      "methodology": "Description of research methods used",
      "contributions": [
        "Novel contribution 1",
        "Novel contribution 2"
      ],
      "limitations": "Identified limitations or gaps",
      "relevance_score": "High/Medium/Low",
      "key_quotes": [
        "Important quote 1",
        "Important quote 2"
      ]
    }
  ],
  "synthesis": {
    "common_themes": ["Theme 1", "Theme 2"],
    "contradictions": ["Contradiction 1"],
    "research_gaps": ["Gap 1", "Gap 2"],
    "quality_assessment": "Overall quality evaluation"
  },
  "recommendations": [
    "Recommendation 1 for further research",
    "Recommendation 2 for practical application"
  ]
}
```

## Analysis Guidelines
- Be thorough but concise in your analysis
- Support claims with specific evidence from the papers
- Maintain academic rigor and objectivity
- Identify both strengths and weaknesses
- Focus on actionable insights

## Reasoning Guidelines
- Keep internal reasoning focused on analysis quality
- Don't narrate every reading step
- Use reasoning for complex synthesis decisions
- Prioritize evidence-based conclusions

Execute this workflow systematically for each paper provided.
"""

# ============================================================================
# IAM ROLE ASSUMPTION FOR S3 ACCESS
# ============================================================================


def assume_s3_access_role(
    role_arn: str, session_name: str = "AnalyzerAgentS3Access"
) -> boto3.client:
    """
    Assume an IAM role and return an S3 client with the assumed credentials.

    Args:
        role_arn: ARN of the IAM role to assume
        session_name: Name for the assumed role session

    Returns:
        boto3 S3 client with assumed role credentials
    """
    logger.info(f"(IAM) Assuming role: {role_arn}")

    try:
        sts_client = boto3.client("sts")

        # Assume the role
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name,
            DurationSeconds=3600,  # 1 hour session
        )

        # Extract temporary credentials
        credentials = response["Credentials"]
        logger.info(f"(Success) Role assumed successfully. Session: {session_name}")

        # Create S3 client with assumed role credentials
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
        )

        logger.info("(Success) S3 client created with assumed role credentials")
        return s3_client

    except ClientError as e:
        logger.error(f"(Error) Failed to assume role: {e}")
        raise
    except Exception as e:
        logger.error(f"(Error) Unexpected error during role assumption: {e}")
        raise


def initialize_s3_client(role_arn: Optional[str] = None) -> boto3.client:
    """
    Initialize S3 client, optionally with role assumption.

    Args:
        role_arn: Optional IAM role ARN to assume. If None, uses default credentials.

    Returns:
        boto3 S3 client
    """
    if role_arn:
        logger.info("(IAM) Initializing S3 client with role assumption")
        return assume_s3_access_role(role_arn)
    else:
        logger.info("(IAM) Initializing S3 client with default credentials")
        return boto3.client("s3")


# ============================================================================
# S3 DOCUMENT DOWNLOAD TOOL
# ============================================================================


@tool
def download_s3_document(s3_uri: str) -> str:
    """
    Download a document from S3 using its URI.

    Args:
        s3_uri: S3 URI in format 's3://bucket-name/prefix/filename.txt'

    Returns:
        The text content of the document
    """
    global s3_client

    logger.info(f"(Tool) Downloading document from S3: {s3_uri}")

    # Ensure S3 client is initialized
    if s3_client is None:
        error_msg = "S3 client not initialized. Agent initialization may have failed."
        logger.error(f"(Error) {error_msg}")
        return json.dumps({"error": error_msg})

    try:
        # Parse S3 URI
        if not s3_uri.startswith("s3://"):
            return json.dumps(
                {"error": f"Invalid S3 URI format. Must start with 's3://': {s3_uri}"}
            )

        # Remove 's3://' prefix and split bucket and key
        path = s3_uri[5:]
        parts = path.split("/", 1)

        if len(parts) != 2:
            return json.dumps(
                {
                    "error": f"Invalid S3 URI format. Expected 's3://bucket/key': {s3_uri}"
                }
            )

        bucket_name, object_key = parts

        # Download from S3
        logger.info(f"(S3) Fetching from bucket='{bucket_name}', key='{object_key}'")
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)

        # Read content
        content = response["Body"].read().decode("utf-8")
        logger.info(f"(Success) Downloaded {len(content)} characters from {s3_uri}")

        return content

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        logger.error(f"(Error) S3 ClientError: {error_code} - {error_msg}")

        if error_code == "NoSuchKey":
            return json.dumps(
                {"error": f"Document not found at {s3_uri}", "details": error_msg}
            )
        elif error_code == "NoSuchBucket":
            return json.dumps(
                {"error": f"Bucket does not exist: {bucket_name}", "details": error_msg}
            )
        elif error_code == "AccessDenied":
            return json.dumps(
                {
                    "error": f"Access denied to {s3_uri}. Check IAM role permissions.",
                    "details": error_msg,
                }
            )
        else:
            return json.dumps(
                {
                    "error": f"Failed to download from S3: {error_code}",
                    "details": error_msg,
                }
            )

    except Exception as e:
        logger.error(f"(Error) Unexpected error downloading from S3: {e}")
        return json.dumps({"error": f"Unexpected error: {str(e)}"})


# ============================================================================
# SSM HELPER FUNCTIONS
# ============================================================================


def get_ssm_parameters() -> dict:
    """Fetch configuration from AWS SSM Parameter Store."""
    ssm_client = boto3.client("ssm")
    param_names = list(SSM_PARAMETERS_MAP.values())
    logger.info("Fetching configuration from AWS SSM Parameter Store...")

    try:
        response = ssm_client.get_parameters(Names=param_names, WithDecryption=True)
        config = {}
        reverse_map = {v: k for k, v in SSM_PARAMETERS_MAP.items()}

        for param in response.get("Parameters", []):
            env_var_name = reverse_map[param["Name"]]
            config[env_var_name] = param["Value"]

        required_keys = set(SSM_PARAMETERS_MAP.keys())
        missing_keys = required_keys - set(config.keys())
        if missing_keys:
            raise KeyError(f"Missing required SSM parameters: {missing_keys}")

        logger.info("(Success) Configuration loaded successfully from SSM")
        return config

    except ClientError as e:
        logger.error(f"Error fetching parameters from SSM: {e}")
        raise


# ============================================================================
# AGENT INITIALIZATION
# ============================================================================


def initialize_analyzer_agent():
    """
    Initialize the analyzer agent with MCP tools and S3 download capability.
    """
    global s3_client

    logger.info("(Initializing) Initializing Analyzer Agent...")

    # Fetch configuration from SSM
    app_config = get_ssm_parameters()

    # Initialize S3 client with role assumption
    role_arn = app_config.get("S3_ACCESS_ROLE_ARN")
    if role_arn:
        logger.info(f"(IAM) S3 access role ARN found: {role_arn}")
        s3_client = initialize_s3_client(role_arn)
    else:
        logger.warning(
            "(IAM) No S3 access role ARN configured. Using default credentials."
        )
        s3_client = initialize_s3_client()

    # Configure model
    model_id = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
    model = BedrockModel(model_id=model_id, temperature=0.3)

    # Create the agent with S3 download tool
    all_tools = [download_s3_document]
    agent = Agent(model=model, system_prompt=ANALYZER_SYSTEM_PROMPT, tools=all_tools)

    logger.info("(Success) Analyzer Agent initialized successfully")
    return agent


# Initialize agent and MCP client at module level
analyzer_agent = None

try:
    analyzer_agent = initialize_analyzer_agent()
except Exception as e:
    logger.error(f"(Error) Failed to initialize analyzer agent: {e}")
    analyzer_agent = None


# ============================================================================
# QUERY FORMATTING HELPER
# ============================================================================


def format_analysis_query(
    paper_uris: list[str] | str, context: Optional[str] = None
) -> str:
    """
    Format the analysis query for the agent.

    Args:
        paper_uris: Either a single S3 URI string or list of S3 URIs to analyze
        context: Optional context about what to focus on in the analysis

    Returns:
        Formatted query string ready for the agent
    """
    # Normalize to list
    if isinstance(paper_uris, str):
        paper_uris = [paper_uris]

    base_query = f"Analyze the following {len(paper_uris)} paper(s) from S3:\n\n"

    for i, uri in enumerate(paper_uris, 1):
        base_query += f"{i}. {uri}\n"

    if context:
        base_query += f"\nAnalysis Focus: {context}\n"

    base_query += """
WORKFLOW REMINDER:
1. Use the download_s3_document tool to retrieve each paper's full text
2. Carefully analyze the content of each paper
3. Extract key findings, methodologies, and contributions
4. Synthesize insights across papers if multiple papers provided
5. Return results in the specified JSON format

Execute this analysis now."""

    return base_query


# ============================================================================
# DIRECT EXECUTION HELPER (for testing/standalone use)
# ============================================================================


def execute_analysis(
    paper_uris: list[str] | str, context: Optional[str] = None, verbose: bool = True
) -> str:
    """
    Execute an analysis directly using the analyzer agent.

    Args:
        paper_uris: S3 URI(s) of papers to analyze
        context: Optional analysis context
        verbose: If True, prints progress information

    Returns:
        Agent response as string
    """
    if analyzer_agent is None:
        error_msg = "(Error) Cannot execute - agent not initialized"
        if verbose:
            print(error_msg)
        return error_msg

    try:
        # Format the query
        formatted_query = format_analysis_query(paper_uris, context)

        if verbose:
            print("=" * 80)
            print("(Query) Executing analysis:")
            print("-" * 80)
            if isinstance(paper_uris, list):
                print(f"Papers to analyze: {len(paper_uris)}")
                for uri in paper_uris:
                    print(f"  - {uri}")
            else:
                print(f"Paper: {paper_uris}")
            if context:
                print(f"Context: {context}")
            print("=" * 80)
            print()

        # Execute the analysis
        response = analyzer_agent(formatted_query)

        if verbose:
            print("\n(Response) AGENT RESPONSE:")
            print(response)
            print("\n")

        return str(response)

    except Exception as e:
        error_msg = f"(Error) Error: {str(e)}"
        if verbose:
            print(error_msg)
        logger.error(f"Analysis execution failed: {e}")
        return error_msg


# ============================================================================
# STANDALONE TESTING AND CLI
# ============================================================================


def run_test_mode():
    """Run the analyzer agent in test mode with predefined S3 URIs."""
    if analyzer_agent is None:
        print("(Error) Cannot start - agent initialization failed")
        return

    print("=" * 80)
    print("(Test Mode) Analyzer Agent - Test Mode")
    print("=" * 80)
    print()

    # Test with sample S3 URIs (replace with actual URIs in your environment)
    test_uris = [
        "s3://ai-agent-hackathon-processed-pdf-files/2003.10401v1/chunks.json",
        "s3://ai-agent-hackathon-processed-pdf-files/2010.11437v1/chunks.json",
    ]

    test_context = "Focus on deep learning methodologies and their applications"

    print(f"(Info) Testing with {len(test_uris)} papers")
    print()

    # Execute the analysis
    execute_analysis(test_uris, context=test_context, verbose=True)


def cleanup():
    """Clean up resources."""
    global s3_client

    if s3_client:
        logger.info("(Cleanup) Closing S3 client connection...")
        try:
            # S3 client doesn't need explicit cleanup, but we can set it to None
            s3_client = None
            logger.info("(Success) S3 client cleaned up")
        except Exception as e:
            logger.error(f"Error during S3 cleanup: {e}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    import sys

    try:
        # Check command line arguments
        if len(sys.argv) > 1:
            if sys.argv[1] == "test":
                run_test_mode()
            elif sys.argv[1].startswith("s3://"):
                # Direct S3 URI analysis
                uris = sys.argv[1:]
                execute_analysis(uris, verbose=True)
            else:
                print("Usage: python analyzer_agent.py [test|s3://uri1 s3://uri2 ...]")
        else:
            print("Usage: python analyzer_agent.py [test|s3://uri1 s3://uri2 ...]")

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
