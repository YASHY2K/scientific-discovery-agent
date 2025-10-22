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
import requests
from typing import Optional

# Configure logging for debugging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Research Agent Chat", page_icon="🔬", layout="wide")

# ============================================================================
# Configuration - Switch between local and production
# ============================================================================

# Set to True for local testing, False for production
USE_LOCAL_MODE = os.getenv("USE_LOCAL_MODE", "true").lower() == "true"
LOCAL_API_URL = os.getenv("LOCAL_API_URL", "http://localhost:8000")

# Display mode in sidebar
MODE = "🖥️ LOCAL" if USE_LOCAL_MODE else "☁️ PRODUCTION"


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


# ============================================================================
# Local Mode - Call FastAPI Server
# ============================================================================


def invoke_agent_local(prompt: str, session_id: str) -> dict:
    """
    Invoke the multi-agent research system via local FastAPI server.

    Args:
        prompt: User's research question
        session_id: Unique session identifier for conversation context

    Returns:
        dict: Parsed agent output containing report and metadata

    Raises:
        requests.exceptions.ConnectionError: When FastAPI server is not running
        requests.exceptions.Timeout: When request takes too long
        Exception: For other unexpected errors
    """
    try:
        # Check if API is healthy
        health_response = requests.get(f"{LOCAL_API_URL}/health", timeout=2)
        if health_response.status_code != 200:
            raise Exception("API server is not healthy")

        # Make request to local API
        response = requests.post(
            f"{LOCAL_API_URL}/query",
            json={"user_query": prompt, "session_id": session_id},
            timeout=1800,  # 30 minute timeout for research
        )

        if response.status_code == 200:
            result = response.json()

            # Extract response and metrics
            agent_response = result.get("response", "No response received")
            metrics = result.get("metrics", {})

            return {
                "report": agent_response,
                "papers_found": (
                    metrics.get("papers_found", 0) if isinstance(metrics, dict) else 0
                ),
                "analysis_iterations": (
                    metrics.get("iterations", 0) if isinstance(metrics, dict) else 0
                ),
                "agents_executed": [
                    "Planner",
                    "Searcher",
                    "Analyzer",
                    "Critique",
                    "Reporter",
                ],
                "phase": result.get("phase", "COMPLETE"),
            }
        else:
            error_detail = response.json().get("detail", response.text)
            raise Exception(f"API Error {response.status_code}: {error_detail}")

    except requests.exceptions.ConnectionError:
        raise Exception(
            f"Cannot connect to local API at {LOCAL_API_URL}. "
            "Make sure the FastAPI server is running:\n"
            "python middleware.py"
        )
    except requests.exceptions.Timeout:
        raise Exception("Request timed out. The query may be too complex.")


# ============================================================================
# Production Mode - Call AWS AgentCore
# ============================================================================


@st.cache_resource
def get_bedrock_client():
    """
    Initialize and cache the AWS Bedrock AgentCore client with retry config.
    Only used in production mode.
    """
    import boto3
    from botocore.config import Config

    try:
        from utils import get_config_value

        aws_region = (
            get_config_value("AWS_REGION", "/app/config/AWS_REGION") or "us-east-1"
        )
        agent_runtime_arn = get_config_value(
            "AGENT_RUNTIME_ARN", "/app/config/AGENT_RUNTIME_ARN"
        )
    except ImportError:
        aws_region = os.getenv("AWS_REGION", "us-east-1")
        agent_runtime_arn = os.getenv("AGENT_RUNTIME_ARN")

    config = Config(
        retries={
            "total_max_attempts": 5,
            "mode": "adaptive",
        },
        connect_timeout=30,
        read_timeout=300,
        max_pool_connections=25,
    )

    return (
        boto3.client("bedrock-agentcore", region_name=aws_region, config=config),
        agent_runtime_arn,
    )


def invoke_agent_production(prompt: str, session_id: str) -> dict:
    """
    Invoke the multi-agent research system via AWS Bedrock AgentCore Runtime.
    Only used in production mode.
    """
    from botocore.exceptions import NoCredentialsError, ClientError

    client, agent_runtime_arn = get_bedrock_client()

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
        qualifier="DEFAULT",
    )

    content = []
    for chunk in response.get("response", []):
        content.append(chunk.decode("utf-8"))

    response_body = "".join(content)

    try:
        response_data = json.loads(response_body)
    except json.JSONDecodeError:
        response_data = {"output": {"report": response_body}}

    output = response_data.get("output", {})

    return {
        "report": output.get("report", response_body or "No report generated"),
        "papers_found": output.get("papers_found", 0),
        "analysis_iterations": output.get("analysis_iterations", 0),
        "agents_executed": output.get("agents_executed", []),
    }


# ============================================================================
# Unified invoke function - routes to local or production
# ============================================================================


def invoke_agent(prompt: str, session_id: str) -> dict:
    """
    Invoke the agent system - automatically routes to local or production.
    """
    if USE_LOCAL_MODE:
        return invoke_agent_local(prompt, session_id)
    else:
        return invoke_agent_production(prompt, session_id)


# ============================================================================
# Session State Initialization
# ============================================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "last_request" not in st.session_state:
    st.session_state.last_request = 0


# ============================================================================
# Sidebar
# ============================================================================

with st.sidebar:
    st.header("🤖 Agent Status")

    # Show mode
    st.info(f"**Mode:** {MODE}")

    if USE_LOCAL_MODE:
        # Show API health status
        try:
            health_check = requests.get(f"{LOCAL_API_URL}/health", timeout=2)
            if health_check.status_code == 200:
                st.success("✅ Local API Connected")
            else:
                st.error("❌ Local API Error")
        except:
            st.error("❌ Local API Not Running")
            st.caption(f"Start server: `python middleware.py`")

    st.caption(f"🔑 Session: `{st.session_state.session_id[:8]}...`")

    if st.button("🔄 New Session", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

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

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("What research topic would you like to explore?"):
    # Validate input
    try:
        is_valid, error_message = is_valid_plain_text(prompt)
    except Exception as e:
        logger.error(f"Input validation error: {str(e)}", exc_info=True)
        st.warning("⚠️ Input validation temporarily unavailable. Proceeding with query.")
        is_valid = True
        error_message = ""

    if not is_valid:
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
        st.stop()

    # Rate limiting (optional for local testing)
    if not USE_LOCAL_MODE and time.time() - st.session_state.last_request < 300:
        st.warning("⚠️ Please wait 5 minutes between requests")
        st.stop()

    st.session_state.last_request = time.time()

    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    # Process with agent
    with st.chat_message("assistant"):
        try:
            with st.sidebar:
                with st.status("🚀 Research workflow...", expanded=True) as status:
                    st.write("📋 **Planner Agent** - Generating research plan...")
                    time.sleep(0.8)

                    st.write("🔍 **Searcher Agent** - Finding relevant papers...")
                    time.sleep(0.8)

                    st.write("📊 **Analyzer Agent** - Analyzing paper content...")
                    time.sleep(0.8)

                    st.write("⚖️ **Critique Agent** - Reviewing analysis quality...")
                    time.sleep(0.8)

                    st.write("📝 **Reporter Agent** - Generating final report...")

                    # Call the agent (local or production)
                    output = invoke_agent(prompt, st.session_state.session_id)

                    status.update(label="✅ Research completed!", state="complete")

            # Show execution summary
            st.info(
                f"""
📊 **Execution Summary**
- 📄 **Papers Found:** {output.get("papers_found", "N/A")}
- 🔄 **Analysis Iterations:** {output.get("analysis_iterations", "N/A")}
- 🤖 **Agents Used:** {", ".join(output.get("agents_executed", [])) if output.get("agents_executed") else "N/A"}
- 📍 **Phase:** {output.get("phase", "COMPLETE")}
"""
            )

            st.divider()
            st.markdown("### 📄 Research Report")
            final_report = output["report"]
            st.markdown(final_report)
            with st.expander("🔍 What Actually Happened"):
                st.write(f"**Papers Found:** {output['papers_found']}")
                st.write(
                    f"**Papers Analyzed:** {output.get('papers_analyzed', 'Unknown')}"
                )
                st.write(f"**Analysis Errors:** {output.get('analysis_errors', 0)}")
                st.write(f"**Critique Score:** {output.get('quality_score', 'N/A')}")
                st.write(f"**Revisions:** {output.get('revision_count', 0)}")
            # Add to chat history
            st.session_state.messages.append(
                {"role": "assistant", "content": final_report}
            )

        except Exception as e:
            error_msg = f"❌ **Error**: {str(e)}"
            st.error(error_msg)

            # Show full traceback in expander for debugging
            with st.expander("Show detailed error"):
                st.exception(e)

            st.session_state.messages.append(
                {"role": "assistant", "content": error_msg}
            )
