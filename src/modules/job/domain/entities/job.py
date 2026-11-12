"""
Job entity — one posting, normalized from whichever source it came from.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import Field, model_validator
from pymongo import ASCENDING, DESCENDING, IndexModel
from typing_extensions import Self

from src.shared.domain.entities.audited_entity import AuditedEntity

from ..enums.employment_type import EmploymentType


class Job(AuditedEntity):
    """
    A collected job posting.

    Inherits from AuditedEntity: id, is_active, created_at, updated_at,
    created_by, updated_by. The audit stamps stay null — collection is not a
    person — but the shape is the one every table here shares.

    Two visibility flags, and they answer different questions:

    - ``is_active`` — the COLLECTOR's: the source still lists it. A run marks a
      job inactive once its source has not shown it for JOB_STALE_AFTER_DAYS,
      and active again if it reappears.
    - ``is_hidden`` — an ADMIN's moderation decision. A run never changes it, so
      a hidden spam posting stays hidden however often its source repeats it.

    A seeker sees a job when it is active, not hidden and not a duplicate. That
    rule lives in ONE place, ``JobRepository``.

    De-duplication: unique per ``(source_id, external_id)``. The same posting on
    two sources shares a ``fingerprint`` (normalized title + company +
    location); the later copy points at the first through ``duplicate_of_id``
    and is left out of search.

    ``effective_posted_at`` is ``posted_at`` or, when the source gave no
    date, ``first_seen_at`` — the date a job sorts and filters by. It is
    derived on every validation, stored so MongoDB can index and sort on it,
    and never set by hand.

    Collection: jobs
    """

    __collection__ = "jobs"
    __indexes__ = [
        IndexModel(
            [("source_id", ASCENDING), ("external_id", ASCENDING)],
            unique=True,
            name="uq_jobs_source_external",
        ),
        IndexModel([("fingerprint", ASCENDING)], name="ix_jobs_fingerprint"),
        IndexModel(
            [
                ("is_active", ASCENDING),
                ("is_hidden", ASCENDING),
                ("posted_at", DESCENDING),
            ],
            name="ix_jobs_visible_posted",
        ),
        IndexModel(
            [
                ("is_active", ASCENDING),
                ("is_hidden", ASCENDING),
                ("effective_posted_at", DESCENDING),
            ],
            name="ix_jobs_visible_effective_posted",
        ),
        IndexModel(
            [("source_id", ASCENDING), ("last_seen_at", ASCENDING)],
            name="ix_jobs_source_seen",
        ),
        IndexModel([("is_remote", ASCENDING)], name="ix_jobs_is_remote"),
        IndexModel([("employment_type", ASCENDING)], name="ix_jobs_employment_type"),
    ]

    source_id: UUID

    external_id: str = Field(max_length=255)

    title: str = Field(max_length=300)

    company: str = Field(max_length=200)

    location: Optional[str] = Field(default=None, max_length=200)

    is_remote: bool = Field(default=False)

    employment_type: Optional[EmploymentType] = Field(default=None)

    salary_min: Optional[int] = Field(default=None)

    salary_max: Optional[int] = Field(default=None)

    salary_currency: Optional[str] = Field(default=None, max_length=3)

    description: str = Field(default="")

    url: str = Field(max_length=1000, description="Where to apply")

    category: Optional[str] = Field(default=None, max_length=120)

    tags: List[str] = Field(default_factory=list)

    posted_at: Optional[datetime] = Field(default=None)

    first_seen_at: datetime

    last_seen_at: datetime

    fingerprint: str = Field(max_length=64)

    duplicate_of_id: Optional[UUID] = Field(default=None)

    is_hidden: bool = Field(default=False)

    effective_posted_at: Optional[datetime] = Field(
        default=None,
        description="posted_at, or first_seen_at when unstated (derived, for sorting)",
    )

    @model_validator(mode="after")
    def _derive_effective_posted(self) -> Self:
        """Keep ``effective_posted_at`` = ``coalesce(posted_at, first_seen_at)``.

        Written through ``__dict__`` so it does not re-enter validation.
        Assignments to ``posted_at`` elsewhere are not validated (Job has no
        ``validate_assignment``), so ``sync_effective_posted`` is also called
        by the repository before every write.
        """
        self.__dict__["effective_posted_at"] = self.posted_at or self.first_seen_at
        return self

    def sync_effective_posted(self) -> None:
        """Recompute the derived sort date after ``posted_at`` changed."""
        self.__dict__["effective_posted_at"] = self.posted_at or self.first_seen_at

    def __repr__(self) -> str:
        """String representation of Job."""
        return f"<Job(title='{self.title}', company='{self.company}')>"
