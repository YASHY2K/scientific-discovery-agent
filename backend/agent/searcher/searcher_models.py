from pydantic import BaseModel, Field
from typing import List, Literal


class SelectedPaper(BaseModel):
    id: str = Field(
        description="Paper identifier (e.g., arxiv:2401.12345 or s2:paper_id)"
    )
    title: str = Field(description="Paper title")
    authors: List[str] = Field(description="List of paper authors")
    abstract: str = Field(description="Full abstract of the paper")
    source: Literal["arxiv", "semantic_scholar"] = Field(description="Source database")
    published_date: str = Field(description="Publication date in YYYY-MM-DD format")
    pdf_url: str = Field(description="URL to the paper PDF")
    relevance_score: Literal["High", "Medium", "Low"] = Field(
        description="Relevance assessment"
    )
    selection_reason: str = Field(
        description="Explanation for why this paper was selected"
    )
    processing_initiated: bool = Field(
        description="Whether paper processing was initiated"
    )


class SearchResult(BaseModel):
    sub_topic_id: str = Field(description="Sub-topic identifier or 'general_search'")
    search_iterations: int = Field(description="Number of search iterations performed")
    total_papers_found: int = Field(
        description="Total number of papers found across all searches"
    )
    selected_papers: List[SelectedPaper] = Field(
        description="List of selected papers (3-5 papers)"
    )
    papers_processed: int = Field(description="Number of papers sent for processing")
    search_strategy: List[str] = Field(
        description="Step-by-step description of search strategy"
    )
    papers_excluded: str = Field(description="Summary of papers excluded and reasons")
    quality_assessment: str = Field(
        description="Assessment of result quality and confidence"
    )
    recommendations: str = Field(description="Recommendations for further analysis")
