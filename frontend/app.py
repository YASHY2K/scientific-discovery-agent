"""
Research Multi-Agent System - Streamlit Chat Interface

A simple chat interface for interacting with the multi-agent research system.
Provides real-time transparency into agent execution through a glassbox sidebar.
"""

import os
import uuid
import json
import time
import streamlit as st
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

st.set_page_config(page_title="Research Agent Chat", page_icon="🔬", layout="wide")


@st.cache_resource
def get_bedrock_client():
    """
    Initialize and cache the AWS Bedrock AgentCore client.

    Uses @st.cache_resource to prevent recreating the client on every rerun.
    Loads AWS configuration from environment variables.

    Returns:
        boto3.Client: Bedrock AgentCore client
    """
    aws_region = os.getenv("AWS_REGION", "us-east-1")

    return boto3.client("bedrock-agent-runtime", region_name=aws_region)


# Initialize messages list for chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Generate unique session ID for agent context tracking
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())


def invoke_agent(prompt: str, session_id: str) -> dict:
    """
    Invoke the multi-agent research system via AWS Bedrock AgentCore.

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
    agent_runtime_arn = os.getenv("AGENT_RUNTIME_ARN")

    if not agent_runtime_arn:
        raise ValueError("AGENT_RUNTIME_ARN environment variable is not set")

    payload = {
        "input": {
            "prompt": prompt,
            "session_id": session_id,
            "user_id": "streamlit-user",
        }
    }

    response = client.invoke_agent(
        agentId=agent_runtime_arn,
        agentAliasId="TSTALIASID",  # Default test alias
        sessionId=session_id,
        inputText=prompt,
    )

    response_body = ""
    for event in response.get("completion", []):
        if "chunk" in event:
            chunk = event["chunk"]
            if "bytes" in chunk:
                response_body += chunk["bytes"].decode("utf-8")

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
    5. **📝 Reporter** - Generates report
    
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
