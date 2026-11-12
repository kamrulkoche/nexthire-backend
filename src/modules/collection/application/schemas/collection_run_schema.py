"""Collection run Pydantic schemas. Mirrored in `src/interface/admin.interface.ts` (`IRun`)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.modules.job_source.domain.enums.source_type import SourceType

from ...domain.enums.run_status import RunStatus
from ...domain.enums.run_trigger import RunTrigger


class CollectionRunSchema(BaseModel):
    """A run as the run-history screen receives it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    source_name: Optional[str] = None
    source_type: Optional[SourceType] = None
    trigger: RunTrigger
    status: RunStatus
    triggered_by: Optional[UUID] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = Field(default=None, description="Null while running")
    fetched_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    duplicate_count: int = 0
    skipped_count: int = 0
    deactivated_count: int = 0
    error_message: Optional[str] = None


class StartRunSchema(BaseModel):
    """An admin pressing Run now."""

    source_id: UUID
