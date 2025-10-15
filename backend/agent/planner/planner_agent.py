from strands import Agent
from strands.models import BedrockModel
from planner_models import ResearchPlan


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

model_id = "openai.gpt-oss-120b-1:0"

model = BedrockModel(model_id=model_id)


planner_agent = Agent(
    model=model,
    system_prompt=Planner_Agent_prompt,
)

if __name__ == "__main__":
    plan = planner_agent.structured_output(
        output_model=ResearchPlan,
        prompt="Compare reinforcement learning and supervised learning for robotics control",
    )
    print(f"Approach: {plan.research_approach}")
    print(f"Sub-topics: {len(plan.sub_topics)}\n")

    for st in plan.sub_topics:
        print(f"{st.id}:")
        print(f"  Description: {st.description}")
        print(f"  Keywords: {', '.join(st.suggested_keywords)}")
        print(f"  Criteria: {st.success_criteria}")
        print(f"  Focus: {st.search_guidance.focus_on}")
        print()
