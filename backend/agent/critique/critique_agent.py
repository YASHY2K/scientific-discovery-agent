"""
Critique Agent - Research Quality Assurance
Validates analysis quality and identifies gaps requiring revision.
"""

import logging
import json
from typing import Dict, Any, List, Optional

from strands import Agent
from strands.models import BedrockModel

# Enable debug logs
logging.getLogger("strands").setLevel(logging.DEBUG)
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s", handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

# ============================================================================
# CRITIQUE AGENT SYSTEM PROMPT
# ============================================================================

CRITIQUE_SYSTEM_PROMPT = """You are a Research Quality Assurance Specialist.

IMPORTANT: All output MUST use ASCII characters only. Do not use emojis, special characters, or unicode symbols.

Your role is to evaluate the quality and completeness of research analysis.

## Your Evaluation Criteria

### 1. Completeness
- Are all aspects of the research question addressed?
- Do all sub-topics from the plan have adequate analysis?
- Are there missing perspectives or methodologies?

### 2. Accuracy
- Are technical details correctly represented?
- Do findings match the evidence presented?
- Are there contradictions or inconsistencies?

### 3. Balance
- Are multiple perspectives considered?
- Is the analysis objective and unbiased?
- Are limitations and strengths both discussed?

### 4. Depth
- Is the analysis substantive or superficial?
- Are findings supported by evidence?
- Is the reasoning clear and logical?

### 5. Currency
- Are recent developments included?
- Are the papers from appropriate time periods?
- Is the research relevant to the query?

## Output Format

You MUST return a single valid JSON object with this structure:

```json
{
  "verdict": "APPROVED or REVISE",
  "overall_quality_score": 0.0-1.0,
  "evaluation": {
    "completeness": {
      "score": 0.0-1.0,
      "assessment": "brief assessment"
    },
    "accuracy": {
      "score": 0.0-1.0,
      "assessment": "brief assessment"
    },
    "balance": {
      "score": 0.0-1.0,
      "assessment": "brief assessment"
    },
    "depth": {
      "score": 0.0-1.0,
      "assessment": "brief assessment"
    },
    "currency": {
      "score": 0.0-1.0,
      "assessment": "brief assessment"
    }
  },
  "strengths": [
    "Strength 1",
    "Strength 2"
  ],
  "critical_issues": [
    {
      "severity": "high/medium/low",
      "issue": "Description of issue",
      "impact": "Why this matters",
      "required_action": "Specific action needed"
    }
  ],
  "coverage_gaps": [
    {
      "gap": "Missing element",
      "why_important": "Why it matters",
      "suggested_search": "Specific search query to find papers"
    }
  ],
  "required_revisions": [
    {
      "action": "search_more_papers or re_analyze",
      "target": "sub_topic_id or topic",
      "reason": "Why this revision is needed",
      "specific_query": "For search actions: what to search for",
      "additional_focus": "For re_analyze actions: what to focus on"
    }
  ],
  "approval_conditions": [
    "Condition 1 that must be met",
    "Condition 2 that must be met"
  ],
  "overall_assessment": "Brief summary of research quality and recommendations"
}
```

## Decision Logic

### APPROVE if:
- Overall quality score >= 0.75
- No high-severity issues remain
- All sub-topics adequately covered
- Analysis is substantive and well-supported

### REVISE if:
- Quality score < 0.75
- Critical gaps exist
- High-severity issues identified
- Insufficient evidence for claims

## Analysis Guidelines
- Be specific and actionable in feedback
- Avoid vague criticisms ("needs more work")
- Provide concrete suggestions for improvement
- Consider trade-offs between perfection and practicality
- Remember this is iterative (max 2 revision cycles)

## Reasoning Guidelines
- Evaluate based on research standards
- Consider the specific research domain
- Be fair but rigorous in assessment
- Support judgments with evidence
- Focus on impact and importance

Conduct this evaluation systematically based on the plan, analyses, and original query.
"""

# ============================================================================
# AGENT INITIALIZATION
# ============================================================================


def initialize_critique_agent():
    """Initialize the critique agent."""
    logger.info("Initializing Critique Agent...")

    model_id = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"

    model = BedrockModel(model_id=model_id, temperature=0.3)

    critique = Agent(model=model, system_prompt=CRITIQUE_SYSTEM_PROMPT)

    logger.info("Critique Agent initialized")
    return critique


critique_agent = initialize_critique_agent()

# ============================================================================
# CRITIQUE EXECUTION
# ============================================================================


def evaluate_research(
    original_query: str,
    research_plan: Dict[str, Any],
    analyses: Dict[str, Any],
    revision_count: int = 0,
) -> str:
    """
    Evaluate research quality and completeness.

    Args:
        original_query: The original research question
        research_plan: The plan output from planner agent
        analyses: Dictionary of analyses from analyzer agent {subtopic_id: analysis}
        revision_count: How many times this has been revised (0-2)

    Returns:
        JSON string with critique verdict and feedback
    """
    if critique_agent is None:
        logger.error("Critique agent not initialized")
        return json.dumps({"error": "Critique agent not initialized"})

    try:
        logger.info(f"Evaluating research quality (revision_count: {revision_count})")

        # Build evaluation prompt
        evaluation_prompt = f"""Evaluate the quality and completeness of this research analysis.

ORIGINAL RESEARCH QUERY:
{original_query}

RESEARCH PLAN:
{json.dumps(research_plan, indent=2)}

ANALYSES COMPLETED:
{json.dumps({k: v for k, v in analyses.items()}, indent=2)}

REVISION ATTEMPT: {revision_count}/2

Conduct a thorough evaluation based on the criteria and return a JSON object matching the specified format.

If this is revision attempt 2, be more lenient with approval but still identify critical gaps.
"""

        # Call critique agent
        logger.info("Calling critique agent for evaluation")
        result = critique_agent(evaluation_prompt)

        logger.info("Critique evaluation complete")
        return str(result)

    except Exception as e:
        logger.error(f"Critique evaluation error: {e}")
        return json.dumps({"error": str(e)})


# ============================================================================
# PUBLIC INTERFACE
# ============================================================================


def critique(
    original_query: str,
    research_plan: Dict[str, Any],
    analyses: Dict[str, Any],
    revision_count: int = 0,
) -> str:
    """
    Public interface for critiquing research.

    Args:
        original_query: Original research question
        research_plan: Plan from planner agent
        analyses: Analyses from analyzer agent
        revision_count: Current revision attempt (0-2)

    Returns:
        JSON string with critique verdict
    """
    return evaluate_research(original_query, research_plan, analyses, revision_count)


# ============================================================================
# TESTING
# ============================================================================
if __name__ == "__main__":
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

    # Now run critique
    from backend.agent.critique.critique_agent import critique

    result = critique(test_query, test_plan, test_analyses, revision_count=0)
    print("=" * 80)
    print("CRITIQUE RESULT:")
    print("=" * 80)
    print(result)
    print("=" * 80)
