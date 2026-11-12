"""Job Pydantic schemas.

Three shapes, by audience, the way hgs-backend splits public and admin schemas:

- ``JobSummarySchema`` — a card in a list (search, saved, recommendations)
- ``JobDetailSchema`` — the Job Details page
- ``JobAdminSchema`` — moderation, with the collector's bookkeeping

A seeker never receives the moderation flags or the source's own id.
Mirrored by hand in the frontend's `src/interface/job.interface.ts`.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ...domain.enums.employment_type import EmploymentType


class JobSummarySchema(BaseModel):
    """A job as a card in a list."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    company: str
    location: Optional[str] = None
    is_remote: bool = False
    employment_type: Optional[EmploymentType] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    posted_at: Optional[datetime] = None
    first_seen_at: datetime
    source_name: Optional[str] = None
    is_saved: bool = Field(default=False, description="The caller saved this job")
    match_score: Optional[int] = Field(
        default=None, description="The caller's AI match score, if scored"
    )
    is_available: bool = Field(
        default=True,
        description="False once the job is hidden or gone from its source — "
        "still shown on saved jobs and matches, never in search",
    )


class JobDetailSchema(JobSummarySchema):
    """A job on its own page."""

    description: str = ""
    url: str
    category: Optional[str] = None
    last_seen_at: datetime


class JobAdminSchema(JobDetailSchema):
    """A job on the moderation screen."""

    source_id: UUID
    external_id: str
    is_active: bool
    is_hidden: bool
    duplicate_of_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class JobModerationSchema(BaseModel):
    """The one thing an admin changes on a job."""

    is_hidden: bool


class PublicStatsSchema(BaseModel):
    """Counts for the landing page."""

    jobs: int = 0
    companies: int = 0
    sources: int = 0
    new_this_week: int = 0
