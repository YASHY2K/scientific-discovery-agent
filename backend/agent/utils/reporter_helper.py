import logging
from typing import Optional
from datetime import datetime


logging.getLogger("strands").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s", handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


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
