from strands import Agent, tool
from typing import List
from strands.models import BedrockModel
from pydantic import BaseModel, Field
from typing import List, Literal


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


class SearchGuidance(BaseModel):
    focus_on: str = Field(description="What aspects to emphasize in the search")
    must_include: str = Field(description="Required elements that papers must contain")
    avoid: str = Field(description="What to filter out as out of scope")


class SubTopic(BaseModel):
    id: str = Field(description="Unique identifier for the sub-topic")
    description: str = Field(
        description="Clear 1-2 sentence description of what to investigate"
    )
    priority: int = Field(description="Priority level (1=highest, 2=medium, 3=lowest)")
    success_criteria: str = Field(
        description="Specific, measurable target for paper quantity and quality"
    )
    suggested_keywords: List[str] = Field(
        description="3-5 starting keyword suggestions"
    )
    search_guidance: SearchGuidance


class ResearchPlan(BaseModel):
    research_approach: Literal[
        "focused_deep_dive", "comparative_analysis", "comprehensive_survey"
    ] = Field(description="Type of research approach needed")
    sub_topics: List[SubTopic] = Field(
        description="List of sub-topics to investigate (1-3 sub-topics recommended)"
    )


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
