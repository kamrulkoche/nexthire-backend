"""The scoring contract.

A scorer takes one seeker's profile and a short list of jobs and returns a
score, a rationale and skill labels for each. Two implementations live in
``infrastructure/scorers/``: Gemini, and a deterministic keyword heuristic used
when no key is configured or Gemini fails. Use cases depend on this protocol
only, so tests pass a fake and nothing here knows Gemini exists.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Sequence
from uuid import UUID

from src.modules.job.domain.entities.job import Job
from src.modules.preference.domain.entities.job_preference import JobPreference

#: Characters of a job description a scorer is shown. Enough for the
#: requirements section of most postings; bounded so one batch stays cheap.
DESCRIPTION_EXCERPT = 1500


@dataclass(frozen=True)
class SeekerProfile:
    """What a scorer knows about the seeker."""

    keywords: tuple[str, ...] = ()
    excluded_keywords: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    remote_only: bool = False
    employment_types: tuple[str, ...] = ()
    min_salary: Optional[int] = None
    experience_level: Optional[str] = None
    summary: str = ""

    @classmethod
    def from_preferences(cls, prefs: JobPreference) -> "SeekerProfile":
        """Build a profile from the stored preferences row."""
        return cls(
            keywords=tuple(prefs.keywords or ()),
            excluded_keywords=tuple(prefs.excluded_keywords or ()),
            locations=tuple(prefs.locations or ()),
            remote_only=prefs.remote_only,
            employment_types=tuple(prefs.employment_types or ()),
            min_salary=prefs.min_salary,
            experience_level=(
                prefs.experience_level.value if prefs.experience_level else None
            ),
            summary=prefs.profile_summary or "",
        )


@dataclass(frozen=True)
class JobSnapshot:
    """What a scorer knows about a job."""

    id: UUID
    title: str
    company: str
    location: Optional[str]
    is_remote: bool
    employment_type: Optional[str]
    salary_min: Optional[int]
    salary_max: Optional[int]
    salary_currency: Optional[str]
    tags: tuple[str, ...]
    description: str

    @classmethod
    def from_job(cls, job: Job) -> "JobSnapshot":
        """Build a snapshot from a stored job, excerpting its description."""
        assert job.id is not None
        return cls(
            id=job.id,
            title=job.title,
            company=job.company,
            location=job.location,
            is_remote=job.is_remote,
            employment_type=job.employment_type.value if job.employment_type else None,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            salary_currency=job.salary_currency,
            tags=tuple(job.tags or ()),
            description=(job.description or "")[:DESCRIPTION_EXCERPT],
        )


@dataclass(frozen=True)
class ScoredJob:
    """One scorer verdict."""

    job_id: UUID
    score: int
    rationale: str
    matched_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)


class JobScorer(Protocol):
    """Scores jobs for a seeker."""

    @property
    def name(self) -> str:
        """Stored on each match as ``scorer`` — the model id, or ``heuristic``."""
        ...

    async def score(
        self, profile: SeekerProfile, jobs: Sequence[JobSnapshot]
    ) -> List[ScoredJob]:
        """Score each job. May return fewer verdicts than jobs given."""
        ...
