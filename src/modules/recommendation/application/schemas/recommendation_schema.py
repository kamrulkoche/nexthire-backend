"""Recommendation Pydantic schemas. Mirrored in `src/interface/seeker.interface.ts` (`IRecommendation`)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from src.modules.job.application.schemas.job_schema import JobSummarySchema


class RecommendationSchema(BaseModel):
    """One match: the job card plus why it fits."""

    job: JobSummarySchema
    score: int
    rationale: str
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    scorer: str = Field(description="Model id, or `heuristic`")
    is_ai: bool = Field(description="Scored by Gemini rather than the heuristic")
    is_dismissed: bool = False
    scored_at: datetime


class RefreshResultSchema(BaseModel):
    """What one refresh did."""

    scored: int = Field(description="New jobs scored this time")
    candidates: int = Field(description="Jobs considered before the shortlist")
    scorer: str
    fallback_reason: Optional[str] = Field(
        default=None, description="Why Gemini was not used, when it was not"
    )


class DismissSchema(BaseModel):
    """Hide a match from recommendations, or bring it back."""

    dismissed: bool = True
