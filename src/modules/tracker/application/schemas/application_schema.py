"""Job application Pydantic schemas.

Limits mirror `src/helpers/validation/application.schema.ts` in the frontend.
"""

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from ...domain.enums.application_status import ApplicationStatus


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    return value or None


class ApplicationSchema(BaseModel):
    """A tracker row as the Applications screen receives it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: Optional[UUID] = None
    title: str
    company: str
    location: Optional[str] = None
    url: Optional[str] = None
    status: ApplicationStatus
    applied_on: Optional[date] = None
    next_step: Optional[str] = None
    next_step_at: Optional[datetime] = None
    notes: str = ""
    status_changed_at: Optional[datetime] = None
    job_available: bool = Field(
        default=False, description="The linked job is still listed"
    )
    created_at: datetime
    updated_at: datetime


class ApplicationCreateSchema(BaseModel):
    """
    Start tracking an application.

    Either ``job_id`` (title, company, location and URL are copied from the
    job) or ``title`` + ``company`` for a job found elsewhere.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: Optional[UUID] = None
    title: Optional[str] = Field(default=None, min_length=2, max_length=300)
    company: Optional[str] = Field(default=None, min_length=1, max_length=200)
    location: Optional[str] = Field(default=None, max_length=200)
    url: Optional[HttpUrl] = None
    status: ApplicationStatus = ApplicationStatus.INTERESTED
    applied_on: Optional[date] = None
    next_step: Optional[str] = Field(default=None, max_length=200)
    next_step_at: Optional[datetime] = None
    notes: str = Field(default="", max_length=5000)

    @field_validator("location", "next_step", "url", mode="before")
    @classmethod
    def blank_to_none(cls, value: Optional[str]) -> Optional[str]:
        """An untouched optional field arrives as ``""``; store null."""
        return _blank_to_none(value)

    @model_validator(mode="after")
    def job_or_details(self) -> "ApplicationCreateSchema":
        """A job to copy from, or the details to track by hand."""
        if self.job_id is None and not (self.title and self.company):
            raise ValueError("Give either job_id, or title and company")
        return self


class ApplicationUpdateSchema(BaseModel):
    """A partial update. Omitted keys are left alone; null clears a field."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Optional[str] = Field(default=None, min_length=2, max_length=300)
    company: Optional[str] = Field(default=None, min_length=1, max_length=200)
    location: Optional[str] = Field(default=None, max_length=200)
    url: Optional[HttpUrl] = None
    status: Optional[ApplicationStatus] = None
    applied_on: Optional[date] = None
    next_step: Optional[str] = Field(default=None, max_length=200)
    next_step_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=5000)

    @field_validator("location", "next_step", "url", mode="before")
    @classmethod
    def blank_to_none(cls, value: Optional[str]) -> Optional[str]:
        """An emptied field means "clear it"."""
        return _blank_to_none(value)


class ApplicationCountsSchema(BaseModel):
    """Per-status totals for the tracker's tabs and the dashboard."""

    interested: int = 0
    applied: int = 0
    interviewing: int = 0
    offer: int = 0
    hired: int = 0
    rejected: int = 0
    withdrawn: int = 0
    total: int = 0
