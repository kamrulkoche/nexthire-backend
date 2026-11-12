"""Job preference Pydantic schemas.

Limits mirror the frontend's Zod schema in
`src/helpers/validation/preference.schema.ts`; change both together.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.modules.job.domain.enums.employment_type import EmploymentType

from ...domain.enums.experience_level import ExperienceLevel

MAX_LIST_ITEMS = 20
MAX_ITEM_LENGTH = 60
MAX_SUMMARY_LENGTH = 4000


def _clean_list(values: List[str]) -> List[str]:
    """Trim, drop blanks, de-duplicate case-insensitively, keep first spelling."""
    seen: set[str] = set()
    cleaned: List[str] = []
    for value in values:
        item = " ".join(str(value).split())
        if not item:
            continue
        if len(item) > MAX_ITEM_LENGTH:
            raise ValueError(f"Each entry must be at most {MAX_ITEM_LENGTH} characters")
        key = item.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(item)
    if len(cleaned) > MAX_LIST_ITEMS:
        raise ValueError(f"At most {MAX_LIST_ITEMS} entries")
    return cleaned


class PreferenceSchema(BaseModel):
    """A seeker's preferences as the Preferences screen receives them.

    ``exists`` is false until the seeker first saves; the other fields then
    hold the defaults, so the form always has something to render.
    """

    model_config = ConfigDict(from_attributes=True)

    exists: bool = True
    keywords: List[str] = Field(default_factory=list)
    excluded_keywords: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    remote_only: bool = False
    employment_types: List[EmploymentType] = Field(default_factory=list)
    min_salary: Optional[int] = None
    experience_level: Optional[ExperienceLevel] = None
    profile_summary: str = ""
    notify_on_match: bool = True
    updated_at: Optional[datetime] = None


class PreferenceUpdateSchema(BaseModel):
    """The whole Preferences form. A PUT: every field is replaced."""

    model_config = ConfigDict(str_strip_whitespace=True)

    keywords: List[str] = Field(default_factory=list)
    excluded_keywords: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    remote_only: bool = False
    employment_types: List[EmploymentType] = Field(default_factory=list)
    min_salary: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    experience_level: Optional[ExperienceLevel] = None
    profile_summary: str = Field(default="", max_length=MAX_SUMMARY_LENGTH)
    notify_on_match: bool = True

    @field_validator("keywords", "excluded_keywords", "locations")
    @classmethod
    def clean_lists(cls, values: List[str]) -> List[str]:
        """Normalize the free-text lists."""
        return _clean_list(values)

    @field_validator("employment_types")
    @classmethod
    def unique_types(cls, values: List[EmploymentType]) -> List[EmploymentType]:
        """Drop repeats, keep order."""
        return list(dict.fromkeys(values))
