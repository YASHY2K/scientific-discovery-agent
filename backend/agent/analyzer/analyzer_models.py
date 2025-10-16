from pydantic import BaseModel, Field
from typing import List, Literal

from pydantic import BaseModel, Field
from typing import List, Literal


class PaperAnalysis(BaseModel):
    s3_uri: str = Field(description="S3 URI where the paper is stored")
    title: str = Field(description="Extracted or inferred title of the paper")
    key_findings: List[str] = Field(
        description="List of key findings with supporting evidence"
    )
    methodology: str = Field(description="Description of research methods used")
    contributions: List[str] = Field(description="List of novel contributions")
    limitations: str = Field(
        description="Identified limitations or gaps in the research"
    )
    relevance_score: Literal["High", "Medium", "Low"] = Field(
        description="Assessment of paper's relevance"
    )
    key_quotes: List[str] = Field(description="Important quotes from the paper")


class Synthesis(BaseModel):
    common_themes: List[str] = Field(
        description="Common themes identified across papers"
    )
    contradictions: List[str] = Field(description="Contradictions found between papers")
    research_gaps: List[str] = Field(description="Identified gaps in research")
    quality_assessment: str = Field(
        description="Overall quality evaluation of the papers"
    )


class AnalysisResponse(BaseModel):
    analysis_id: str = Field(description="Unique identifier for this analysis")
    papers_analyzed: List[PaperAnalysis] = Field(description="List of analyzed papers")
    synthesis: Synthesis = Field(description="Synthesis of findings across papers")
    recommendations: List[str] = Field(
        description="Recommendations for further research and application"
    )
