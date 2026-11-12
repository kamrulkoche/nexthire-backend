"""
SavedJob entity — a seeker's bookmark on a job.
"""

from typing import Optional
from uuid import UUID

from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from src.shared.domain.entities.base_entity import BaseEntity


class SavedJob(BaseEntity):
    """
    One job one seeker saved.

    A plain ``BaseEntity`` (id, created_at): a bookmark is created and deleted,
    never edited except for its note, and an unsave is a real DELETE — there is
    nothing worth keeping about a bookmark someone removed. That is the one
    hard delete in this service, and it touches only the caller's own document.

    Unique per (user, job), so saving twice is idempotent rather than a second
    document.

    Collection: saved_jobs
    """

    __collection__ = "saved_jobs"
    __indexes__ = [
        IndexModel(
            [("user_id", ASCENDING), ("job_id", ASCENDING)],
            unique=True,
            name="uq_saved_jobs_user_job",
        ),
        IndexModel(
            [("user_id", ASCENDING), ("created_at", DESCENDING)],
            name="ix_saved_jobs_user_created",
        ),
        IndexModel([("job_id", ASCENDING)], name="ix_saved_jobs_job"),
    ]

    user_id: UUID

    job_id: UUID

    note: Optional[str] = Field(default=None, max_length=500)

    def __repr__(self) -> str:
        """String representation of SavedJob."""
        return f"<SavedJob(user_id='{self.user_id}', job_id='{self.job_id}')>"
