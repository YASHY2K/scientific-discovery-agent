"""
Reporter Agent - Research Report Generation
Compiles analyses into comprehensive research reports using a modular,
section-by-section approach.
"""

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

# CRITICAL: Import the @tool decorator and ToolContext
from strands import Agent, tool, ToolContext
from strands.models import BedrockModel

# Enable debug logs (optional, but good for testing)
logging.getLogger("strands").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s", handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


# ============================================================================
# MODULAR PROMPTS
# ============================================================================

# This is the base instruction given to ALL section-writing agents.
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
        user_query = tool_context.agent.state.get("user_query", "")
        research_plan = tool_context.agent.state.get("research_plan", {})
        analyses = tool_context.agent.state.get("analyses", {})
        critique_results = tool_context.agent.state.get("critique_results", {})

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
        for block in response.message.content:
            if block.type == "text":
                section_content += block.text

        # 6. Save this section's content into state
        generated_sections = tool_context.agent.state.get("generated_sections", {})
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

        generated_sections = tool_context.agent.state.get("generated_sections", {})

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
        user_query = tool_context.agent.state.get("user_query", "Research Report")
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


# ============================================================================
# LEGACY FUNCTIONS (No longer used by orchestrator)
# ============================================================================


def report(*args, **kwargs):
    """
    Legacy function, no longer called by the chunked orchestrator.
    """
    logger.warning(
        "Legacy report function called. This should not happen in chunked mode."
    )
    return "Error: Legacy report function called."


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    # This file is intended to be imported as a module, not run directly.
    print("Reporter.py is a module and is ready to be imported by the orchestrator.")
    print("It provides the following tools:")
    print("- write_report_section_tool")
    print("- finalize_report_tool")
