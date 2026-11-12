"""What a connector hands back: one posting, already normalized.

A connector's whole job is to turn its source's format into these. It never
touches the database; ``ExecuteRunUseCase`` decides what to insert, update or
skip. That keeps every connector testable with nothing but a canned response.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.modules.job.domain.enums.employment_type import EmploymentType


@dataclass(frozen=True)
class CollectedJob:
    """One posting as a connector read it.

    Attributes:
        external_id: The source's own id for the posting; unique per source
        title: Job title, plain text
        company: Hiring company, plain text
        url: Where a seeker applies
        description: Plain text — connectors strip HTML before building this
        location: Free-text location, if any
        is_remote: Whether the posting says it is remote
        employment_type: Normalized through ``EmploymentType.from_source``
        salary_min / salary_max / salary_currency: When the source states them
        category: The source's category label, if any
        tags: Short skill or topic labels
        posted_at: When the source says it was posted (UTC)
    """

    external_id: str
    title: str
    company: str
    url: str
    description: str = ""
    location: Optional[str] = None
    is_remote: bool = False
    employment_type: Optional[EmploymentType] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: Optional[str] = None
    category: Optional[str] = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    posted_at: Optional[datetime] = None
