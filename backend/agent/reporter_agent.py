"""
Reporter Agent - Research Report Generation
Compiles analyses into comprehensive research reports.
"""

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from strands import Agent
from strands.models import BedrockModel

# Enable debug logs
logging.getLogger("strands").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s", handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

# ============================================================================
# REPORTER AGENT SYSTEM PROMPT
# ============================================================================

REPORTER_SYSTEM_PROMPT = """You are a Technical Report Writer specializing in academic research synthesis.

Your role is to compile structured analyses into a comprehensive, well-formatted research report.

## Report Structure

Create a markdown report with these sections:

### 1. Executive Summary
- 3-4 paragraphs for general audience
- Focus on key findings and their impact
- Plain language, avoid jargon

### 2. Introduction
- Restate original research query in formal terms
- Explain methodology and approach
- Define scope and limitations

### 3. Main Findings (One section per sub-topic)
- Organized by the sub-topics from the research plan
- Present key findings for each
- Include quantitative results with tables if available
- Support claims with evidence

### 4. Cross-Study Synthesis
- Identify common themes across papers
- Note contradictions and explain them
- Highlight methodological innovations
- Discuss practical implications

### 5. Research Gaps and Future Directions
- Identify unanswered questions
- Suggest areas for further research
- Prioritize gaps by importance

### 6. Conclusions
- Summarize key takeaways (5-7 bullet points)
- Practical implications for practitioners
- Recommendations for implementation or future work

### 7. References
- Full bibliography in consistent format
- Include all papers analyzed
- Organized alphabetically

### 8. Appendix (Optional)
- Search queries used
- Selection criteria
- Paper count by source
- Quality metrics

## Writing Guidelines

- Use clear, professional academic tone
- Define technical terms on first use
- Use active voice where possible
- Support all claims with citations
- Organize information logically
- Use headers to guide readers
- Include transitions between sections

## Output Format

Return ONLY the markdown report text. Do NOT include any JSON or metadata.

The report should be:
- Complete and standalone (reader doesn't need other docs)
- Well-formatted with proper markdown
- Between 2000-4000 words
- Professional and rigorous

Begin writing the report now.
"""

# ============================================================================
# AGENT INITIALIZATION
# ============================================================================


def initialize_reporter_agent():
    """Initialize the reporter agent."""
    logger.info("Initializing Reporter Agent...")

    model_id = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"

    model = BedrockModel(
        model_id=model_id,
        temperature=0.5,  # Slightly higher for more natural writing
    )

    reporter = Agent(model=model, system_prompt=REPORTER_SYSTEM_PROMPT)

    logger.info("Reporter Agent initialized")
    return reporter


reporter_agent = initialize_reporter_agent()

# ============================================================================
# REPORT GENERATION
# ============================================================================


def generate_report(
    original_query: str,
    research_plan: Dict[str, Any],
    analyses: Dict[str, Any],
    critique_feedback: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate comprehensive research report.

    Args:
        original_query: Original research question
        research_plan: Plan from planner agent
        analyses: Analyses from analyzer agent {subtopic_id: analysis}
        critique_feedback: Optional feedback from critique agent

    Returns:
        Markdown formatted report as string
    """
    if reporter_agent is None:
        logger.error("Reporter agent not initialized")
        return "Error: Reporter agent not initialized"

    try:
        logger.info("Generating research report")

        # Build report generation prompt
        report_prompt = f"""Generate a comprehensive research report based on this research analysis.

ORIGINAL RESEARCH QUERY:
{original_query}

RESEARCH PLAN:
{json.dumps(research_plan, indent=2)}

ANALYSES (by sub-topic):
{json.dumps(analyses, indent=2)}

{"CRITIQUE FEEDBACK:" + json.dumps(critique_feedback, indent=2) if critique_feedback else ""}

Create a professional markdown report that synthesizes all this information into a coherent narrative.
The report should be complete, well-structured, and suitable for academic or professional audiences.

Start writing the report now:
"""

        # Call reporter agent
        logger.info("Calling reporter agent for report generation")
        result = reporter_agent(report_prompt)

        logger.info("Report generation complete")
        return str(result)

    except Exception as e:
        logger.error(f"Report generation error: {e}")
        return f"Error generating report: {str(e)}"


# ============================================================================
# REPORT UTILITIES
# ============================================================================


def save_report(report_text: str, filename: Optional[str] = None) -> str:
    """
    Save report to file.

    Args:
        report_text: The markdown report text
        filename: Optional filename (default: report_TIMESTAMP.md)

    Returns:
        Path to saved file
    """
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"research_report_{timestamp}.md"

    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(report_text)
        logger.info(f"Report saved to {filename}")
        return filename
    except Exception as e:
        logger.error(f"Error saving report: {e}")
        return f"Error: Could not save report ({str(e)})"


def format_report_metadata(
    original_query: str, num_papers: int, num_subtopics: int
) -> str:
    """
    Create report metadata header.

    Args:
        original_query: Original research question
        num_papers: Total papers analyzed
        num_subtopics: Number of sub-topics researched

    Returns:
        Markdown formatted metadata
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    metadata = f"""---
title: Research Report
query: {original_query}
generated: {timestamp}
papers_analyzed: {num_papers}
subtopics_covered: {num_subtopics}
---

"""
    return metadata


# ============================================================================
# PUBLIC INTERFACE
# ============================================================================


def report(
    original_query: str,
    research_plan: Dict[str, Any],
    analyses: Dict[str, Any],
    critique_feedback: Optional[Dict[str, Any]] = None,
    save_to_file: bool = False,
) -> str:
    """
    Public interface for generating research report.

    Args:
        original_query: Original research question
        research_plan: Plan from planner agent
        analyses: Analyses from analyzer agent
        critique_feedback: Optional feedback from critique
        save_to_file: Whether to save report to file

    Returns:
        Markdown report text (or filename if saved)
    """
    report_text = generate_report(
        original_query, research_plan, analyses, critique_feedback
    )

    if save_to_file:
        return save_report(report_text)

    return report_text


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    # Example usage
    test_query = "Impact of transformer models on time-series forecasting"

    test_plan = {
        "research_approach": "comparative_analysis",
        "sub_topics": [
            {
                "id": "transformer_architectures",
                "description": "How transformers adapted for time-series",
                "search_guidance": {
                    "focus_on": "Architectural innovations",
                    "must_include": "Empirical results",
                    "avoid": "Theory without experiments",
                },
            },
            {
                "id": "comparative_results",
                "description": "Benchmark comparisons with LSTM and other methods",
                "search_guidance": {
                    "focus_on": "Quantitative benchmarks",
                    "must_include": "Performance metrics",
                    "avoid": "Claims without numbers",
                },
            },
        ],
    }

    test_analyses = {
        "transformer_architectures": {
            "key_findings": [
                "Transformers achieve 15-22% improvement over LSTM on standard benchmarks",
                "Multi-head attention enables capturing long-range dependencies",
                "Hybrid CNN-Transformer architectures show promising results",
            ],
            "methodology": "Comprehensive review of 15 papers from 2020-2024",
            "quantitative_results": {
                "benchmark": "M4 Competition",
                "metric": "SMAPE",
                "transformer_score": 12.3,
                "lstm_baseline": 14.1,
            },
        },
        "comparative_results": {
            "key_findings": [
                "Data efficiency trade-off: transformers need 5-10x more data",
                "Computational overhead: 2-3x higher training time than LSTM",
                "Recent hybrid methods show better efficiency",
            ],
            "methodology": "Analysis of 12 benchmark studies",
            "quantitative_results": {
                "transformer_accuracy": 0.92,
                "lstm_accuracy": 0.87,
                "training_time_ratio": 2.5,
            },
        },
    }

    result = report(test_query, test_plan, test_analyses, save_to_file=False)

    print("Generated Report:")
    print("=" * 80)
    print(result)
    print("=" * 80)
