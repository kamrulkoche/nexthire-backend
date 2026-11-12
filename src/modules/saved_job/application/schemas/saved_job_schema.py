"""Saved job Pydantic schemas. Mirrored in `src/interface/seeker.interface.ts` (`ISavedJob`)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.modules.job.application.schemas.job_schema import JobSummarySchema


class SavedJobSchema(BaseModel):
    """A bookmark with the job it points at."""

    job_id: UUID
    note: Optional[str] = None
    saved_at: datetime
    job: JobSummarySchema


class SaveJobSchema(BaseModel):
    """Saving a job, with an optional private note."""

    model_config = ConfigDict(str_strip_whitespace=True)

    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def blank_to_none(cls, value: Optional[str]) -> Optional[str]:
        """An emptied note is no note."""
        return value or None
