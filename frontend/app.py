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

USE_LOCAL_MODE = os.getenv("USE_LOCAL_MODE", "true").lower() == "true"
LOCAL_API_URL = os.getenv("LOCAL_API_URL", "http://localhost:8080")
MODE = "🖥️ LOCAL" if USE_LOCAL_MODE else "☁️ PRODUCTION"


def is_valid_plain_text(text: str) -> tuple[bool, str]:
    import re

    if not text or text.strip() == "":
        return (
            False,
            "Special characters and symbols are not allowed. Please use only letters, numbers, and basic punctuation.",
        )
    allowed_pattern = re.compile(r"^[a-zA-Z0-9\s.,!?;:'\"-\(\)\[\]&@#%/\\+]+$")
    if not allowed_pattern.match(text):
        emoji_pattern = re.compile(
            "["
            "\U0001f600-\U0001f64f"
            "\U0001f300-\U0001f5ff"
            "\U0001f680-\U0001f6ff"
            "\U0001f1e0-\U0001f1ff"
            "\U0001f900-\U0001f9ff"
            "]+",
            flags=re.UNICODE,
        )
        if emoji_pattern.search(text):
            return False, "Emojis are not allowed in research queries."
        else:
            return (
                False,
                "Special characters and symbols are not allowed. Please use only letters, numbers, and basic punctuation.",
            )
    return True, ""


# ============================================================================
# Local Mode - Call AgentCore Container (use /invocations)
# ============================================================================


def invoke_agent_local(prompt: str, session_id: str) -> dict:
    try:
        response = requests.post(
            f"{LOCAL_API_URL}/invocations",
            json={"user_query": prompt, "session_id": session_id},
            headers={"Content-Type": "application/json"},
            timeout=1800,
        )
        if response.status_code == 200:
            result = response.json()
            return {
                "report": result.get("report", result.get("output", "No response")),
                "papers_found": result.get("papers_found", 0),
                "analysis_iterations": result.get("analysis_iterations", 0),
                "agents_executed": result.get(
                    "agents_executed",
                    ["Planner", "Searcher", "Analyzer", "Critique", "Reporter"],
                ),
                "phase": result.get("phase", "COMPLETE"),
                "papers_analyzed": result.get("papers_analyzed", 0),
                "analysis_errors": result.get("analysis_errors", 0),
                "quality_score": result.get("quality_score", "N/A"),
                "revision_count": result.get("revision_count", 0),
            }
        else:
            raise Exception(f"AgentCore Error {response.status_code}: {response.text}")

    except requests.exceptions.ConnectionError as e:
        raise Exception(
            f"Cannot connect to AgentCore at {LOCAL_API_URL}. "
            "Make sure the container is running:\n\n"
            "agentcore launch --local\n\n"
            f"Error: {str(e)}"
        )
    except requests.exceptions.Timeout:
        raise Exception(
            "Request timed out after 30 minutes. The query may be too complex."
        )
    except Exception as e:
        logger.error(f"Unexpected error invoking agent: {str(e)}", exc_info=True)
        raise


# ============================================================================
# Production Mode - Call AWS AgentCore
# ============================================================================


@st.cache_resource
def get_bedrock_client():
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
        retries={"total_max_attempts": 5, "mode": "adaptive"},
        connect_timeout=30,
        read_timeout=300,
        max_pool_connections=25,
    )
    return (
        boto3.client("bedrock-agentcore", region_name=aws_region, config=config),
        agent_runtime_arn,
    )


def invoke_agent_production(prompt: str, session_id: str) -> dict:
    from botocore.exceptions import NoCredentialsError, ClientError

    client, agent_runtime_arn = get_bedrock_client()
    if not agent_runtime_arn:
        raise ValueError("AGENT_RUNTIME_ARN environment variable is not set")
    payload = json.dumps(
        {
            "user_query": prompt,
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
        "phase": output.get("phase", "COMPLETE"),
        "papers_analyzed": output.get("papers_analyzed", 0),
        "analysis_errors": output.get("analysis_errors", 0),
        "quality_score": output.get("quality_score", "N/A"),
        "revision_count": output.get("revision_count", 0),
    }


# ============================================================================
# Unified invoke function - routes to local or production
# ============================================================================


def invoke_agent(prompt: str, session_id: str) -> dict:
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
    st.info(f"**Mode:** {MODE}")

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

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("What research topic would you like to explore?"):
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

    if not USE_LOCAL_MODE and time.time() - st.session_state.last_request < 300:
        st.warning("⚠️ Please wait 5 minutes between requests")
        st.stop()

    st.session_state.last_request = time.time()

    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

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
                    output = invoke_agent(prompt, st.session_state.session_id)
                    status.update(label="✅ Research completed!", state="complete")
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
            st.session_state.messages.append(
                {"role": "assistant", "content": final_report}
            )
        except Exception as e:
            error_msg = f"❌ **Error**: {str(e)}"
            st.error(error_msg)
            with st.expander("Show detailed error"):
                st.exception(e)
            st.session_state.messages.append(
                {"role": "assistant", "content": error_msg}
            )
