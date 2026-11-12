"""
CollectionRun entity — one attempt to read one source.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from src.shared.domain.entities.base_entity import BaseEntity

from ..enums.run_status import RunStatus
from ..enums.run_trigger import RunTrigger


class CollectionRun(BaseEntity):
    """
    A run of one source's connector, and what it did.

    The run-history screen reads these. A ``BaseEntity`` (id, created_at): a
    run is a record of what happened, written while it happens and never
    edited or deleted afterwards.

    Counts:
        fetched: postings the connector returned
        created: new jobs stored
        updated: known jobs refreshed
        duplicates: new jobs marked duplicates of another source's copy
        skipped: postings the connector could not use
        deactivated: jobs this source has stopped listing, marked inactive

    Collection: collection_runs
    """

    __collection__ = "collection_runs"
    __indexes__ = [
        IndexModel(
            [("source_id", ASCENDING), ("started_at", DESCENDING)],
            name="ix_collection_runs_source_started",
        ),
        IndexModel([("status", ASCENDING)], name="ix_collection_runs_status"),
        IndexModel([("started_at", DESCENDING)], name="ix_collection_runs_started"),
    ]

    source_id: UUID

    trigger: RunTrigger

    status: RunStatus = Field(default=RunStatus.RUNNING)

    triggered_by: Optional[UUID] = Field(
        default=None, description="The admin who pressed Run now; null when scheduled"
    )

    started_at: datetime

    finished_at: Optional[datetime] = Field(default=None)

    fetched_count: int = Field(default=0)
    created_count: int = Field(default=0)
    updated_count: int = Field(default=0)
    duplicate_count: int = Field(default=0)
    skipped_count: int = Field(default=0)
    deactivated_count: int = Field(default=0)

    error_message: Optional[str] = Field(default=None, max_length=500)

    def __repr__(self) -> str:
        """String representation of CollectionRun."""
        return f"<CollectionRun(source_id='{self.source_id}', status='{self.status}')>"
