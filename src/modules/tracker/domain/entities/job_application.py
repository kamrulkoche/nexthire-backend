"""
JobApplication entity — one entry in a seeker's application tracker.
"""

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import Field
from pymongo import ASCENDING, IndexModel

from src.shared.domain.entities.audited_entity import AuditedEntity

from ..enums.application_status import ApplicationStatus


class JobApplication(AuditedEntity):
    """
    A seeker's application to a job.

    Linked to a collected job when there is one (``job_id``), but SNAPSHOTS
    its title, company, location and URL at creation — the same move
    hgs-backend's job applications make when they snapshot each answer with
    the label it was asked under. A source can drop the posting, an admin can
    hide it; the tracker still reads correctly. A seeker can also track an
    application to a job we never collected: ``job_id`` is then null.

    Soft-deleted through ``is_active``, as every delete in hgs-backend is.

    ``applied_on`` is a calendar date; BSON has none, so it is stored as a
    UTC-midnight datetime (see ``MongoDocument.to_document``).

    Collection: job_applications
    """

    __collection__ = "job_applications"
    __indexes__ = [
        IndexModel(
            [("user_id", ASCENDING), ("status", ASCENDING)],
            name="ix_job_applications_user_status",
        ),
        IndexModel([("job_id", ASCENDING)], name="ix_job_applications_job"),
    ]

    user_id: UUID

    job_id: Optional[UUID] = None

    title: str = Field(max_length=300)

    company: str = Field(max_length=200)

    location: Optional[str] = Field(default=None, max_length=200)

    url: Optional[str] = Field(default=None, max_length=1000)

    status: ApplicationStatus = ApplicationStatus.INTERESTED

    applied_on: Optional[date] = None

    next_step: Optional[str] = Field(default=None, max_length=200)

    next_step_at: Optional[datetime] = None

    notes: str = ""

    status_changed_at: Optional[datetime] = None

    def __repr__(self) -> str:
        """String representation of JobApplication."""
        return f"<JobApplication(title='{self.title}', status='{self.status}')>"
