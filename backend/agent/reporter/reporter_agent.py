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

from ..utils.reporter_helper import save_report

# Enable debug logs
logging.getLogger("strands").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s", handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


REPORTER_SYSTEM_PROMPT = """You are a Technical Report Writer specializing in academic research synthesis.

CRITICAL: All output MUST use ASCII characters only. Do not use emojis, special characters, or unicode symbols in your reports.

Your role is to compile structured analyses into a comprehensive, well-formatted research report with the paper references cited using the paper urls.

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
- Paper urls must be included for each reference

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
    test_query = "Deep learning approaches for semantic segmentation: comparing architectural innovations"

    test_plan = {
        "research_approach": "comparative_analysis",
        "sub_topics": [
            {
                "id": "adaptive_network_architectures",
                "description": "Novel approaches to handling scale variance and task-specific adaptation in segmentation",
                "priority": 1,
                "success_criteria": "At least 8-10 papers on dynamic or adaptive architectures",
                "search_guidance": {
                    "focus_on": "Architectural innovations for handling variable inputs, data-dependent routing, task-adaptive mechanisms",
                    "must_include": "Quantitative results on Cityscapes or PASCAL datasets, computational efficiency metrics",
                    "avoid": "Generic segmentation architectures without adaptive properties, theoretical work without empirical validation",
                },
            },
            {
                "id": "few_shot_learning_segmentation",
                "description": "Methods for semantic segmentation with limited labeled data",
                "priority": 1,
                "success_criteria": "At least 6-8 papers on few-shot or meta-learning for segmentation",
                "search_guidance": {
                    "focus_on": "Few-shot learning protocols, meta-learning approaches, parameter efficiency, PASCAL-5i benchmark results",
                    "must_include": "1-shot and 5-shot performance metrics, comparison with baseline methods",
                    "avoid": "Image classification few-shot methods, theoretical meta-learning without segmentation application",
                },
            },
            {
                "id": "computational_efficiency",
                "description": "Trade-offs between accuracy and computational cost in modern segmentation architectures",
                "priority": 2,
                "success_criteria": "At least 5-6 papers discussing FLOPs, parameters, inference time, or efficiency-accuracy trade-offs",
                "search_guidance": {
                    "focus_on": "Parameter efficiency, computational budgets, inference latency, model compression, hardware deployment",
                    "must_include": "Specific numbers: FLOPs counts, parameter counts, runtime measurements",
                    "avoid": "Efficiency claims without quantitative measurements, only theoretical complexity analysis",
                },
            },
        ],
    }

    test_analyses = {
        "adaptive_network_architectures": {
            "sub_topic_id": "adaptive_network_architectures",
            "papers_analyzed": 8,
            "papers_analyzed_count": 8,
            "analyzed_papers": [
                {
                    "paper_id": "2003.10401v1",
                    "title": "Learning Dynamic Routing for Semantic Segmentation",
                    "authors": ["Yanwei Li", "Lin Song", "Yukang Chen", "Zeming Li"],
                    "findings_relevant_to_criteria": [
                        {
                            "criterion": "Architectural innovations for handling variable inputs",
                            "finding": "Proposes soft conditional gate for data-dependent forward path selection",
                            "evidence": "Achieves 5.8% improvement over DeepLab V3 on Cityscapes with similar computational budget (45G FLOPs)",
                        },
                        {
                            "criterion": "Computational efficiency metrics",
                            "finding": "Reduces computational cost to 37.6% of maximum with Dynamic-A configuration",
                            "evidence": "FLOPs reduced from 71.6G (Dynamic-Raw) to 44.9G (Dynamic-A) with only 0.6% accuracy drop",
                        },
                        {
                            "criterion": "Quantitative results on Cityscapes",
                            "finding": "Achieves 80.7% mIoU on Cityscapes test set when combined with PSP module",
                            "evidence": "Outperforms Auto-Deep Lab (80.4%) with fewer parameters and computational overhead",
                        },
                    ],
                    "limitations": "Mainly evaluated on Cityscapes; limited exploration of real-time deployment scenarios",
                },
                {
                    "paper_id": "2010.11437v1",
                    "title": "Task-Adaptive Feature Transformer for Few-Shot Segmentation",
                    "authors": [
                        "Jun Seo",
                        "Young-Hyun Park",
                        "Sung-Whan Yoon",
                        "Jaekyun Moon",
                    ],
                    "findings_relevant_to_criteria": [
                        {
                            "criterion": "Task-adaptive mechanisms",
                            "finding": "Uses meta-learned reference vectors with linear transformation to adapt features to task",
                            "evidence": "Achieves state-of-the-art on PASCAL-5i with only 4,096 additional parameters for 1-way segmentation",
                        },
                        {
                            "criterion": "Parameter efficiency",
                            "finding": "Requires minimal learnable parameters compared to competitors",
                            "evidence": "TAFT: 4,096 params vs SG-One: 1.8M, CANet: 1.2M, PGNet: significantly more",
                        },
                    ],
                    "limitations": "Does not provide FLOPs analysis; limited computational cost discussion",
                },
            ],
            "cross_topic_synthesis": {
                "common_themes": [
                    "Both papers address reducing parameters while maintaining or improving accuracy",
                    "Focus on practical efficiency: parameter count, computational budget, real-world feasibility",
                ],
                "contradictions": [
                    "Dynamic Routing focuses on architectural flexibility; TAFT focuses on feature transformation",
                    "Different design philosophy: routing vs. adaptation",
                ],
                "research_gaps": [
                    "Limited direct comparison between dynamic routing and task-adaptive approaches",
                    "Few papers combine both approaches",
                    "Mobile/edge deployment considerations largely unexplored",
                ],
            },
            "technical_summary": "Recent advances in semantic segmentation emphasize adaptive mechanisms to handle diverse inputs. Dynamic routing enables data-dependent path selection for scale variance, while task-adaptive transformers convert features to task-agnostic spaces. Both achieve significant parameter efficiency.",
            "confidence_metrics": {
                "analysis_completeness": 0.82,
                "data_quality": 0.88,
                "synthesis_confidence": 0.79,
                "overall_confidence": 0.83,
            },
        },
        "few_shot_learning_segmentation": {
            "sub_topic_id": "few_shot_learning_segmentation",
            "papers_analyzed": 7,
            "papers_analyzed_count": 7,
            "analyzed_papers": [
                {
                    "paper_id": "2010.11437v1",
                    "title": "Task-Adaptive Feature Transformer for Few-Shot Segmentation",
                    "findings_relevant_to_criteria": [
                        {
                            "criterion": "5-shot performance metrics",
                            "finding": "Achieves 63.5% mIoU on PASCAL-5i 5-shot segmentation",
                            "evidence": "Outperforms PGNet (58.5%) and CANet (57.1%) by significant margins (5.0-6.4% absolute gain)",
                        },
                        {
                            "criterion": "1-shot performance metrics",
                            "finding": "Achieves 52.1% mIoU on PASCAL-5i 1-shot segmentation",
                            "evidence": "Binary IoU metric shows 70.0% for 1-shot, state-of-the-art on this metric",
                        },
                        {
                            "criterion": "Meta-learning protocol",
                            "finding": "Uses episodic meta-learning with support and query sets",
                            "evidence": "Reference vectors meta-learned and updated per episode, enabling task conditioning",
                        },
                    ],
                    "limitations": "1-shot mIoU slightly lower than CANet and PGNet on some splits; primarily evaluated on PASCAL-5i only",
                }
            ],
            "cross_topic_synthesis": {
                "common_themes": [
                    "Meta-learning approaches essential for few-shot adaptation",
                    "Prototype-based methods show competitive results",
                    "PASCAL-5i is standard benchmark",
                ],
                "contradictions": [],
                "research_gaps": [
                    "Limited papers on few-shot segmentation with other datasets",
                    "Few comparisons with transfer learning baselines",
                    "Real-world scenarios (different domains, object types) unexplored",
                ],
            },
            "technical_summary": "Few-shot segmentation remains challenging, with TAFT showing strong 5-shot results but more modest 1-shot performance. Meta-learning and prototype-based approaches dominate the field.",
            "confidence_metrics": {
                "analysis_completeness": 0.65,
                "data_quality": 0.72,
                "synthesis_confidence": 0.68,
                "overall_confidence": 0.68,
            },
        },
        "computational_efficiency": {
            "sub_topic_id": "computational_efficiency",
            "papers_analyzed": 5,
            "papers_analyzed_count": 5,
            "analyzed_papers": [
                {
                    "paper_id": "2003.10401v1",
                    "title": "Learning Dynamic Routing for Semantic Segmentation",
                    "findings_relevant_to_criteria": [
                        {
                            "criterion": "FLOPs counts and trade-offs",
                            "finding": "Dynamic routing achieves FLOPs reduction with maintained accuracy",
                            "evidence": "Dynamic-A: 44.9G FLOPs vs Deep Lab V3 modeled: 42.5G, with 1.6% accuracy gain (71.6% to 72.8%)",
                        },
                        {
                            "criterion": "Parameter efficiency",
                            "finding": "Parameters scale appropriately with model size",
                            "evidence": "Dynamic models: 4.1-4.5M params vs static architectures: 2.9-6.1M",
                        },
                    ],
                    "limitations": "Does not report inference time; focus is on training FLOPs rather than deployment metrics",
                },
                {
                    "paper_id": "2010.11437v1",
                    "title": "Task-Adaptive Feature Transformer for Few-Shot Segmentation",
                    "findings_relevant_to_criteria": [
                        {
                            "criterion": "Parameter efficiency for few-shot",
                            "finding": "TAFT adds minimal parameters to existing architectures",
                            "evidence": "Only 4,096 parameters for 1-way segmentation; easily plugged into DeepLab V3+",
                        }
                    ],
                    "limitations": "No FLOPs analysis; no inference latency measurements; efficiency gains focus purely on parameter count",
                },
            ],
            "cross_topic_synthesis": {
                "common_themes": [
                    "Parameter efficiency is achievable without significant accuracy loss",
                    "Modular approaches (plugging into existing architectures) are effective",
                ],
                "contradictions": [],
                "research_gaps": [
                    "CRITICAL: No inference latency or real-time deployment metrics",
                    "CRITICAL: No memory usage analysis (peak memory, cache requirements)",
                    "CRITICAL: No hardware-specific analysis (GPU/TPU/CPU deployment)",
                    "No comparison with model quantization or pruning approaches",
                    "Limited analysis of energy efficiency for edge devices",
                ],
            },
            "technical_summary": "Training efficiency is well-studied, but deployment efficiency remains understudied. Papers focus on FLOPs and parameters but lack inference latency, memory usage, and hardware considerations critical for real-world deployment.",
            "confidence_metrics": {
                "analysis_completeness": 0.55,
                "data_quality": 0.70,
                "synthesis_confidence": 0.60,
                "overall_confidence": 0.62,
            },
        },
    }

    result = report(test_query, test_plan, test_analyses, save_to_file=False)

    print("Generated Report:")
    print("=" * 80)
    print(result)
    print("=" * 80)
