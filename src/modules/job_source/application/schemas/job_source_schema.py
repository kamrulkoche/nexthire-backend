"""Job source Pydantic schemas.

Admin only — sources are never shown to seekers by anything but name. The
config is validated per type by ``normalize_source_config`` here, so a bad
setting is a 422 naming ``config``; the use cases apply it again so a script
cannot bypass the schema.

Mirrored by hand in the frontend's `src/interface/admin.interface.ts` (`ISource`) and
`helpers/validation/source.schema.ts`.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from src.modules.collection.domain.enums.run_status import RunStatus
from src.shared.domain.slug import normalize_slug

from ...domain.entities.job_source import MAX_SCHEDULE_MINUTES, MIN_SCHEDULE_MINUTES
from ...domain.enums.source_type import SourceType
from ...domain.services.source_config import normalize_source_config


class JobSourceAdminSchema(BaseModel):
    """A source as the Sources screen receives it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    source_type: SourceType
    config: dict[str, Any]
    is_enabled: bool
    schedule_minutes: int
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[RunStatus] = None
    is_running: bool = Field(
        default=False, description="A run holds this source's claim right now"
    )
    active_jobs: int = Field(default=0, description="Live jobs from this source")
    created_at: datetime
    updated_at: datetime


class JobSourceCreateSchema(BaseModel):
    """What the Sources screen sends to add a source."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=80)
    source_type: SourceType
    config: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True
    schedule_minutes: int = Field(
        default=360, ge=MIN_SCHEDULE_MINUTES, le=MAX_SCHEDULE_MINUTES
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        """The shared slug rule, at the schema layer."""
        return normalize_slug(value)

    @field_validator("config")
    @classmethod
    def validate_config(
        cls, value: dict[str, Any], info: ValidationInfo
    ) -> dict[str, Any]:
        """Normalize the config against its type's rules.

        A field validator (not a model validator) so a bad setting is reported
        under ``config`` rather than the whole request. ``source_type`` is
        declared first, so it is already in ``info.data``; if it failed its own
        validation it is absent, and that error is the one to report.
        """
        source_type = info.data.get("source_type")
        if source_type is None:
            return value
        return normalize_source_config(source_type, value)


class JobSourceUpdateSchema(BaseModel):
    """
    A partial update. Omitted keys are left alone.

    ``source_type`` is not here: a source's type decides what its config means
    and which jobs it owns, so changing it would make it a different source.
    Add a new one instead. The config is checked against the stored type by
    the use case, since only it knows that type.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    config: Optional[dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    schedule_minutes: Optional[int] = Field(
        default=None, ge=MIN_SCHEDULE_MINUTES, le=MAX_SCHEDULE_MINUTES
    )
