"""
JobSource entity — one place jobs are collected from, as an admin configured it.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import ConfigDict, Field, field_validator
from pymongo import ASCENDING, IndexModel

from src.modules.collection.domain.enums.run_status import RunStatus
from src.shared.domain.entities.audited_entity import AuditedEntity
from src.shared.domain.slug import normalize_slug

from ..enums.source_type import SourceType

#: Shortest and longest interval between scheduled runs, in minutes. The floor
#: keeps us polite to free public APIs; the ceiling is a week.
MIN_SCHEDULE_MINUTES = 15
MAX_SCHEDULE_MINUTES = 10080


class JobSource(AuditedEntity):
    """
    A configured job source.

    Inherits from AuditedEntity: id, is_active (the soft-delete flag),
    created_at, updated_at, created_by, updated_by.

    Attributes:
        name: Label on the admin screens
        slug: Stable identifier, unique, the shared slug rule
        source_type: Which connector reads it
        config: Connector settings, normalized by ``source_config.py``
        is_enabled: Whether the scheduler runs it. Separate from ``is_active``:
            a paused source still shows on the Sources screen; a deleted one
            does not
        schedule_minutes: Interval between scheduled runs
        next_run_at: When it is next due; null means "as soon as possible"
        last_run_at / last_run_status: The latest run, denormalized for the list
        locked_until: The run claim. A source is claimed by an atomic UPDATE
            that only succeeds while this is null or past, so two processes can
            never run it at once; a crashed run frees it when the time passes.

    Collection: job_sources
    """

    __collection__ = "job_sources"
    __indexes__ = [
        IndexModel([("slug", ASCENDING)], unique=True, name="uq_job_sources_slug"),
        IndexModel([("source_type", ASCENDING)], name="ix_job_sources_source_type"),
        IndexModel(
            [
                ("is_active", ASCENDING),
                ("is_enabled", ASCENDING),
                ("next_run_at", ASCENDING),
            ],
            name="ix_job_sources_due",
        ),
    ]

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    name: str = Field(max_length=120)

    slug: str = Field(max_length=80)

    source_type: SourceType

    config: dict[str, Any] = Field(default_factory=dict)

    is_enabled: bool = Field(default=True)

    schedule_minutes: int = Field(default=360)

    next_run_at: Optional[datetime] = Field(default=None)

    last_run_at: Optional[datetime] = Field(default=None)

    last_run_status: Optional[RunStatus] = Field(default=None)

    locked_until: Optional[datetime] = Field(default=None)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        """The shared slug rule, at the entity layer."""
        return normalize_slug(value)

    @field_validator("schedule_minutes")
    @classmethod
    def validate_schedule(cls, value: int) -> int:
        """Keep the interval inside the polite range."""
        if not MIN_SCHEDULE_MINUTES <= value <= MAX_SCHEDULE_MINUTES:
            raise ValueError(
                f"schedule_minutes must be between {MIN_SCHEDULE_MINUTES} "
                f"and {MAX_SCHEDULE_MINUTES}"
            )
        return value

    def __repr__(self) -> str:
        """String representation of JobSource."""
        return f"<JobSource(slug='{self.slug}', type='{self.source_type}')>"
