import json
from strands import Agent, tool
from strands.models import BedrockModel
from .planner_models import ResearchPlan


Planner_Agent_prompt = """
        You are a Research Planning Specialist that MUST output ONLY structured JSON.

        CRITICAL INSTRUCTIONS:
        1. YOUR ENTIRE RESPONSE MUST BE VALID JSON.
        2. DO NOT include any natural language text, explanations, or non-JSON content.
        3. NO markdown, no formatting, no introductory text.
        4. JUST the JSON object matching this schema exactly:

        {
            "research_approach": "focused_deep_dive" | "comparative_analysis" | "comprehensive_survey",
            "sub_topics": [
                {
                    "id": "ST1",  // Use sequential numbers ST1, ST2, etc.
                    "description": "Clear description of what to investigate",
                    "priority": 1,  // 1=highest, 2=medium, 3=lowest
                    "success_criteria": "Specific, measurable target",
                    "suggested_keywords": ["keyword1", "keyword2", "keyword3"],
                    "search_guidance": {
                        "focus_on": "What aspects to emphasize",
                        "must_include": "Required elements in papers",
                        "avoid": "What to exclude as out of scope"
                    }
                }
            ]
        }

        Guidelines for plan generation:

        1. TESTING MODE - CRITICAL INSTRUCTIONS:
           - Create EXACTLY ONE sub-topic
           - Use the main query as the sub-topic description
           - Keep it simple and focused
           - Do not decompose or expand the query
           - Do not create multiple aspects or comparisons

        2. Sub-topic requirements (ONE ONLY):
           - Assign ID "ST1"
           - Use query directly as description
           - Set priority 1
           - Include 1-2 keywords only
           - Keep success criteria simple
           - Basic search guidance

        3. Success criteria for testing:
           - "Find 1 relevant paper"
           - Keep it minimal for testing

        4. Search guidance for testing:
           focus_on: Main concept only
           must_include: Core topic
           avoid: Complex requirements

        REMEMBER: Output ONLY the JSON object. No other text or explanation.
"""


model_id = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"  # Corrected Model ID
model = BedrockModel(model_id=model_id)

planner_agent = Agent(
    model=model,
    system_prompt=Planner_Agent_prompt,
)


# --- NEW: STRUCTURED EXECUTION FUNCTION ---
def execute_planning(query: str) -> str:
    """
    Builds a structured prompt and executes the planning agent.

    Args:
        query: The raw user research query.

    Returns:
        A JSON string in the format expected by the orchestrator
    """
    structured_prompt = f"""Please create a comprehensive research plan for the following query.
Analyze its complexity, determine the best approach, and decompose it into independent sub-topics with clear search guidance.

USER QUERY: "{query}"
"""

    print("Calling Planner Agent with structured prompt...")

    # Call the agent with the structured prompt
    plan = planner_agent.structured_output(
        output_model=ResearchPlan, prompt=structured_prompt
    )

    # Convert to orchestrator expected format
    return json.dumps(plan.model_dump())


if __name__ == "__main__":
    # Now the main block calls the new execution function
    user_query = (
        "Compare reinforcement learning and supervised learning for robotics control"
    )

    plan = execute_planning(user_query)
    print(plan)

    print(f"\nApproach: {plan.research_approach}")
    print(f"Sub-topics: {len(plan.sub_topics)}\n")

    for st in plan.sub_topics:
        print(f"{st.id}:")
        print(f"  Description: {st.description}")
        print(f"  Keywords: {', '.join(st.suggested_keywords)}")
        print(f"  Criteria: {st.success_criteria}")
        print(f"  Focus: {st.search_guidance.focus_on}")
        print()
