from pydantic import BaseModel, Field
from typing import List, Literal


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
