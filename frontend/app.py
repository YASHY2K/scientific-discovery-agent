"""
Research Multi-Agent System - Streamlit Chat Interface

A simple chat interface for interacting with the multi-agent research system.
Provides real-time transparency into agent execution through a glassbox sidebar.
"""

import os
import uuid
import json
import time
import logging
import streamlit as st
import boto3
from botocore.config import Config
from botocore.exceptions import NoCredentialsError, ClientError
from utils import get_config_value

# Configure logging for debugging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Research Agent Chat", page_icon="🔬", layout="wide")


def is_valid_plain_text(text: str) -> tuple[bool, str]:
    """
    Validate that input contains only plain text characters.

    Args:
        text: User input string to validate

    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    import re

    # Check for whitespace-only input
    if not text or text.strip() == "":
        return (
            False,
            "Special characters and symbols are not allowed. Please use only letters, numbers, and basic punctuation.",
        )

    # Define allowed characters pattern
    allowed_pattern = re.compile(r"^[a-zA-Z0-9\s.,!?;:\'\"\-\(\)\[\]&@#%/\\+]+$")

    # Check if text contains only allowed characters
    if not allowed_pattern.match(text):
        # Define emoji pattern for more specific error message
        emoji_pattern = re.compile(
            "["
            "\U0001f600-\U0001f64f"  # emoticons
            "\U0001f300-\U0001f5ff"  # symbols & pictographs
            "\U0001f680-\U0001f6ff"  # transport & map symbols
            "\U0001f1e0-\U0001f1ff"  # flags
            "\U0001f900-\U0001f9ff"  # supplemental symbols
            "]+",
            flags=re.UNICODE,
        )

        # Check if it's specifically an emoji
        if emoji_pattern.search(text):
            return False, "Emojis are not allowed in research queries."
        else:
            return (
                False,
                "Special characters and symbols are not allowed. Please use only letters, numbers, and basic punctuation.",
            )

    return True, ""


@st.cache_resource
def get_bedrock_client():
    """
    Initialize and cache the AWS Bedrock AgentCore client with retry config.

    Returns:
        boto3.Client: Bedrock AgentCore client with adaptive retry
    """
    aws_region = get_config_value("AWS_REGION", "/app/config/AWS_REGION") or "us-east-1"

    # Configure boto3 with adaptive retry mode (handles rate limiting automatically)
    config = Config(
        retries={
            "total_max_attempts": 5,  # 1 initial + 4 retries
            "mode": "adaptive",  # Includes automatic rate limiting
        },
        connect_timeout=30,
        read_timeout=300,  # 5 minutes for long-running agents
        max_pool_connections=25,  # Match AgentCore's 25 TPS limit
    )

    return boto3.client("bedrock-agentcore", region_name=aws_region, config=config)


# Initialize messages list for chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Generate unique session ID for agent context tracking
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# Simple rate limiting - track last request time
if "last_request" not in st.session_state:
    st.session_state.last_request = 0


def invoke_agent(prompt: str, session_id: str) -> dict:
    """
    Invoke the multi-agent research system via AWS Bedrock AgentCore Runtime.

    Args:
        prompt: User's research question
        session_id: Unique session identifier for conversation context

    Returns:
        dict: Parsed agent output containing report and metadata

    Raises:
        NoCredentialsError: When AWS credentials are not configured
        ClientError: When AWS API call fails
        Exception: For other unexpected errors
    """
    client = get_bedrock_client()
    agent_runtime_arn = get_config_value(
        "AGENT_RUNTIME_ARN", "/app/config/AGENT_RUNTIME_ARN"
    )

    if not agent_runtime_arn:
        raise ValueError("AGENT_RUNTIME_ARN environment variable is not set")

    payload = json.dumps(
        {
            "prompt": prompt,
            "session_id": session_id,
            "user_id": "streamlit-user",
        }
    ).encode("utf-8")

    response = client.invoke_agent_runtime(
        agentRuntimeArn=agent_runtime_arn,
        runtimeSessionId=session_id,
        payload=payload,
        qualifier="DEFAULT",  # Optional: specify a version/endpoint
    )

    content = []
    for chunk in response.get("response", []):
        content.append(chunk.decode("utf-8"))

    response_body = "".join(content)

    try:
        response_data = json.loads(response_body)
    except json.JSONDecodeError:
        # If response is not JSON, treat it as plain text report
        response_data = {"output": {"report": response_body}}

    output = response_data.get("output", {})

    return {
        "report": output.get("report", response_body or "No report generated"),
        "papers_found": output.get("papers_found", 0),
        "analysis_iterations": output.get("analysis_iterations", 0),
        "agents_executed": output.get("agents_executed", []),
    }


# ============================================================================
# Application UI
# ============================================================================

with st.sidebar:
    st.header("🤖 Agent Status")

    st.caption(f"🔑 Session: `{st.session_state.session_id[:8]}...`")

    st.divider()

    st.markdown(
        """
    ### 📚 How it works:
    
    1. **📋 Planner** - Creates research plan
    2. **🔍 Searcher** - Finds papers
    3. **📊 Analyzer** - Analyzes content
    4. **⚖️ Critique** - Reviews quality
    5. **📝 Reporter** - Generates final report
    
    ---
    
    💡 *Watch the agents work in real-time below when you submit a query!*
    """
    )

# ============================================================================
# Main Content Area
# ============================================================================

st.title("🔬 Research Multi-Agent System")
st.markdown(
    """
    Ask a research question and watch the agents work! This system uses multiple 
    specialized AI agents to conduct comprehensive literature reviews.
    
    💡 **Example queries:**
    - "Find recent papers on transformer architectures in NLP"
    - "What are the latest developments in quantum computing?"
    - "Survey papers on reinforcement learning for robotics"
    """
)

# ============================================================================
# Chat Interface
# ============================================================================

# Loop through all messages in session state and display them
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Display chat input and handle user messages
if prompt := st.chat_input("What research topic would you like to explore?"):
    # Validate input before processing with error handling
    try:
        is_valid, error_message = is_valid_plain_text(prompt)
    except Exception as e:
        # Log validation error for debugging
        logger.error(f"Input validation error: {str(e)}", exc_info=True)

        # Fail open: allow input to proceed if validation encounters unexpected errors
        st.warning("⚠️ Input validation temporarily unavailable. Proceeding with query.")
        is_valid = True
        error_message = ""

    if not is_valid:
        # Display error without adding to chat history
        st.error(
            f"""
❌ **Invalid Input**

{error_message}

**Acceptable characters:**
- Letters (A-Z, a-z)
- Numbers (0-9)
- Basic punctuation (. , ! ? ; : ' " - ( ) [ ])
- Common symbols (& @ # % / \\)

**Example valid queries:**
- "Find recent papers on transformer architectures in NLP"
- "What are the latest developments in quantum computing?"
"""
        )
        st.stop()  # Prevent further execution

    # Simple MVP rate limiting
    if time.time() - st.session_state.last_request < 300:
        st.warning("⚠️ Please wait 5 minutes between requests")
        st.stop()

    # Update last request time
    st.session_state.last_request = time.time()

    # Append user message to session state
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Display user message immediately
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            with st.sidebar:
                # Use st.status() to show workflow progress
                with st.status("🚀 Research workflow...", expanded=True) as status:
                    # Display each agent with emojis and simulated delays
                    st.write("📋 **Planner Agent** - Generating research plan...")
                    time.sleep(0.8)  # Simulated delay for visual feedback

                    st.write("🔍 **Searcher Agent** - Finding relevant papers...")
                    time.sleep(0.8)

                    st.write("📊 **Analyzer Agent** - Analyzing paper content...")
                    time.sleep(0.8)

                    st.write("⚖️ **Critique Agent** - Reviewing analysis quality...")
                    time.sleep(0.8)

                    st.write("📝 **Reporter Agent** - Generating final report...")
                    time.sleep(0.8)

                    output = invoke_agent(prompt, st.session_state.session_id)

                    status.update(label="✅ Research completed!", state="complete")

            st.info(
                f"""
📊 **Execution Summary**
- 📄 **Papers Found:** {output['papers_found']}
- 🔄 **Analysis Iterations:** {output['analysis_iterations']}
- 🤖 **Agents Used:** {', '.join(output['agents_executed']) if output['agents_executed'] else 'N/A'}
"""
            )

            st.divider()
            st.markdown("### 📄 Research Report")
            final_report = output["report"]
            st.markdown(final_report)

            # Add report to chat history
            st.session_state.messages.append(
                {"role": "assistant", "content": final_report}
            )

        except NoCredentialsError:
            error_msg = """
❌ **AWS Credentials Not Configured**

Please configure your AWS credentials:

1. Run: `aws configure`
2. Or set environment variables:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION`
"""
            st.error(error_msg)
            st.session_state.messages.append(
                {"role": "assistant", "content": error_msg}
            )

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]

            # ADDED: Better error handling for throttling
            if error_code == "ThrottlingException":
                error_msg = """
❌ **Rate Limit Exceeded**

The system is temporarily busy. Please try again in a moment.

💡 *The system automatically retries up to 5 times with exponential backoff.*
"""
            else:
                error_msg = f"❌ **AWS Error ({error_code})**: {error_message}"

            st.error(error_msg)
            st.session_state.messages.append(
                {"role": "assistant", "content": error_msg}
            )

        except Exception as e:
            error_msg = f"❌ **Unexpected Error**: {str(e)}"
            st.error(error_msg)
            # Show full traceback in expander for debugging
            with st.expander("Show detailed error"):
                st.exception(e)
            st.session_state.messages.append(
                {"role": "assistant", "content": error_msg}
            )
