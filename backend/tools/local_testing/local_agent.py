import os
import json
import google.generativeai as genai
from urllib.parse import urlparse, urlunparse
import sys
from typing import List

# Adjust sys.path for local imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from tools.search_arxiv.app import search_papers
from tools.local_testing.extract_text import (
    lambda_handler as extract_pdf_text_batch_handler,
)

# --- Configure the Gemini client ---
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY environment variable not set!")
genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-1.5-flash")


# --- Internal Utility Function ---
def convert_arxiv_url_to_pdf(url: str) -> str:
    # ... (Keep the convert_arxiv_url_to_pdf function exactly as it was)
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip("/").split("/")
    if len(path_parts) >= 2 and path_parts[0] == "abs":
        path_parts[0] = "pdf"
        if not path_parts[-1].endswith(".pdf"):
            path_parts[-1] = f"{path_parts[-1]}.pdf"
        new_path = "/" + "/".join(path_parts)
        return urlunparse((parsed_url.scheme, parsed_url.netloc, new_path, "", "", ""))
    return url


# --- Helper to simulate Lambda invocation ---
class DummyContext:
    def __init__(self):
        self.function_name = "simulated-extract-text-function"


def simulate_extract_pdf_text_lambda(pdf_urls: List[str]):
    event = {"body": json.dumps({"pdf_urls": pdf_urls})}
    context = DummyContext()
    response = extract_pdf_text_batch_handler(event, context)
    if response.get("statusCode") == 200:
        return json.loads(response["body"])
    else:
        raise Exception(f"Lambda simulation error: {response.get('body')}")


# --- Tool Registry ---
tools = {
    "search_arxiv": {
        "function": search_papers,
        "description": "Searches arXiv for papers. Input: {'query': 'search term'}",
    },
    "extract_pdf_text": {
        "function": simulate_extract_pdf_text_lambda,
        "description": "Extracts text from a LIST of direct PDF URLs. Input: {'pdf_urls': ['url1', 'url2']}",
    },
}

# --- Internal Utilities ---
internal_utilities = {
    "convert_to_pdf_url": {
        "function": convert_arxiv_url_to_pdf,
        "description": "Converts a single arXiv abstract URL to its direct PDF URL. Input: {'url': 'abstract_url'}",
    }
}


def run_agent_turn(prompt: str, conversation_history: list):
    print("...Agent is thinking...")
    tool_descriptions = "\n".join(
        [f"- `{name}`: {info['description']}" for name, info in tools.items()]
    )
    utility_descriptions = "\n".join(
        [
            f"- `{name}`: {info['description']}"
            for name, info in internal_utilities.items()
        ]
    )

    # --- ENHANCED PROMPT (VERSION 3) ---
    system_prompt = f"""
    You are a diligent AI research assistant. Your goal is to fully complete the user's request by calling tools and utilities in a logical sequence.

    AVAILABLE EXTERNAL TOOLS:
    {tool_descriptions}

    AVAILABLE INTERNAL UTILITIES:
    {utility_descriptions}

    RULES:
    1.  Examine the conversation history, especially the LAST tool output, to decide the next logical step.
    2.  You must continue to use tools until the original user goal is fully completed.
    3.  The `extract_pdf_text` tool requires direct PDF URLs. If you see abstract URLs from `search_arxiv`, you MUST use the `convert_to_pdf_url` utility first.
    4.  When calling `extract_pdf_text`, batch all available direct PDF URLs into a single call.
    5.  The `tool_input` key in your JSON response MUST ALWAYS be a JSON object (a dictionary), like `{{'key': 'value'}}`. For the "none" tool, you can use an empty object `{{}}`.
    6.  Once the user's entire request has been satisfied, respond with `tool_to_use: "none"`.

    CONVERSATION HISTORY:
    ---
    {conversation_history}
    ---

    Based on the history and the user's goal, what is the very next single tool or utility you should use?
    Your response MUST be a valid JSON object.

    User's Goal: "{prompt}"
    Your JSON response:
    """
    try:
        response = model.generate_content(system_prompt)
        decision_text = response.text.strip().replace("```json", "").replace("```", "")
        decision = json.loads(decision_text)
    except Exception as e:
        print(
            f"!! Agent Error: Could not parse LLM response. Error: {e}\nRaw Response: {response.text}"
        )
        return None, None

    return decision.get("tool_to_use"), decision.get("tool_input")


if __name__ == "__main__":
    user_goal = "Find papers about 'Tree of Thoughts' on arXiv and then extract the text from the first result."
    conversation_history = [f"USER: {user_goal}"]

    for i in range(10):
        print(f"\n>>>> Turn {i + 1} <<<<")
        tool_name, tool_input = run_agent_turn(user_goal, conversation_history)

        # --- FIX: Check for the "none" tool FIRST ---
        if tool_name == "none":
            print("\n✅ Agent determined the task is complete.")
            break

        # Now, we check if the input is valid for all other tools
        if not isinstance(tool_input, dict):
            print(f"!! Agent Error: tool_input is not a dictionary. Got: {tool_input}")
            conversation_history.append(
                f"AGENT_ERROR: The LLM provided an invalid format for tool_input."
            )
            continue

        if tool_name in tools:
            print(
                f"...Agent decided to use external tool: '{tool_name}' with input: {tool_input}"
            )
            selected_tool = tools[tool_name]["function"]
            try:
                result = selected_tool(**tool_input)
                tool_result_str = json.dumps(result, indent=2)
                print(
                    f"✅ Tool '{tool_name}' Executed Successfully. Result:\n{tool_result_str}"
                )
                conversation_history.append(
                    f"TOOL_OUTPUT ({tool_name}): {tool_result_str}"
                )
            except Exception as e:
                print(f"!! External Tool Execution Error: {e}")
                conversation_history.append(f"TOOL_ERROR ({tool_name}): {e}")

        elif tool_name in internal_utilities:
            print(
                f"...Agent decided to use internal utility: '{tool_name}' with input: {tool_input}"
            )
            selected_utility = internal_utilities[tool_name]["function"]
            try:
                result = selected_utility(**tool_input)
                utility_result_str = str(result)
                print(
                    f"✅ Internal Utility '{tool_name}' Executed Successfully. Result:\n{utility_result_str}"
                )
                conversation_history.append(
                    f"UTILITY_OUTPUT ({tool_name}): {utility_result_str}"
                )
            except Exception as e:
                print(f"!! Internal Utility Execution Error: {e}")
                conversation_history.append(f"UTILITY_ERROR ({tool_name}): {e}")

        else:
            # This case now handles unknown tools, as "none" is already caught.
            print(f"!! Agent Error: Unknown tool or utility '{tool_name}'")
            break
