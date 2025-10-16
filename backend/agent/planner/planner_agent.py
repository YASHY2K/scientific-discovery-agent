from strands import Agent
from strands.models import BedrockModel
from planner.planner_models import ResearchPlan

Planner_Agent_prompt = """
        You are a Research Planning Specialist.

        Use structured output when requested to provide comprehensive research.

        Analyze the query and decide:
        1. Complexity: simple, moderate, or complex?
        2. Approach: focused_deep_dive, comparative_analysis, or comprehensive_survey?
        3. Sub-topics: What independent areas need investigation?

        Key principles:
        - Don't over-decompose: "Latest X papers" = 1 sub-topic
        - Comparisons ("X vs Y"): Usually 2 sub-topics (one per approach)
        - Multi-faceted queries: 3-4 sub-topics for distinct perspectives
        - No overlap: Each sub-topic must be independently investigatable

        For each sub-topic:
        - Provide 3-5 keywords (starting suggestions only)
        - Set realistic success criteria (paper counts based on topic breadth)
        - Give clear search guidance (focus, requirements, exclusions)
        
"""

model_id = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"  # Corrected Model ID
model = BedrockModel(model_id=model_id)

planner_agent = Agent(
    model=model,
    system_prompt=Planner_Agent_prompt,
)


# --- NEW: STRUCTURED EXECUTION FUNCTION ---
def execute_planning(query: str) -> ResearchPlan:
    """
    Builds a structured prompt and executes the planning agent.

    Args:
        query: The raw user research query.

    Returns:
        A structured ResearchPlan object.
    """
    # You can add more context to the prompt if needed in the future
    structured_prompt = f"""Please create a comprehensive research plan for the following query.
Analyze its complexity, determine the best approach, and decompose it into independent sub-topics with clear search guidance.

USER QUERY: "{query}"
"""

    print("📝 Calling Planner Agent with structured prompt...")

    # Call the agent with the structured prompt
    plan = planner_agent.structured_output(
        output_model=ResearchPlan, prompt=structured_prompt
    )

    return plan


if __name__ == "__main__":
    # Now the main block calls the new execution function
    user_query = (
        "Compare reinforcement learning and supervised learning for robotics control"
    )

    plan = execute_planning(user_query)

    print(f"\nApproach: {plan.research_approach}")
    print(f"Sub-topics: {len(plan.sub_topics)}\n")

    for st in plan.sub_topics:
        print(f"{st.id}:")
        print(f"  Description: {st.description}")
        print(f"  Keywords: {', '.join(st.suggested_keywords)}")
        print(f"  Criteria: {st.success_criteria}")
        print(f"  Focus: {st.search_guidance.focus_on}")
        print()
