"""
JobPreference entity — what one seeker is looking for.
"""

from typing import List, Optional
from uuid import UUID

from pydantic import Field
from pymongo import ASCENDING, IndexModel

from src.shared.domain.entities.audited_entity import AuditedEntity

from ..enums.experience_level import ExperienceLevel


class JobPreference(AuditedEntity):
    """
    A seeker's search preferences and profile — one document per user.

    It is what the recommendation pre-filter and the scorer read. The fields
    that are hard filters (``remote_only``, ``employment_types``) narrow the
    candidates in the query; everything else is context for scoring.

    Attributes:
        keywords: Skills and role words to look for ("python", "data engineer")
        excluded_keywords: Words that rule a job out ("unpaid", "php")
        locations: Acceptable locations; empty means anywhere
        remote_only: Only remote jobs
        employment_types: Acceptable ``EmploymentType`` values; empty means any
        min_salary: Lowest acceptable salary, in the seeker's terms
        experience_level: Seniority sought
        profile_summary: Free text about the seeker — what Gemini reads
        notify_on_match: Raise a notification when a run finds strong matches

    Collection: job_preferences
    """

    __collection__ = "job_preferences"
    __indexes__ = [
        IndexModel(
            [("user_id", ASCENDING)], unique=True, name="uq_job_preferences_user"
        ),
    ]

    user_id: UUID

    keywords: List[str] = Field(default_factory=list)

    excluded_keywords: List[str] = Field(default_factory=list)

    locations: List[str] = Field(default_factory=list)

    remote_only: bool = False

    employment_types: List[str] = Field(default_factory=list)

    min_salary: Optional[int] = None

    experience_level: Optional[ExperienceLevel] = None

    profile_summary: str = ""

    notify_on_match: bool = True

    def __repr__(self) -> str:
        """String representation of JobPreference."""
        return f"<JobPreference(user_id='{self.user_id}')>"
