"""Lead Finder Pydantic schemas.

Mirrored by hand in nexthire-frontend's `src/interface/lead.interface.ts`;
the request limits are mirrored in `src/helpers/validation/lead.schema.ts`.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from ...domain.enums import ExportFormat, LeadStatus, SearchStatus

#: Keyword length limits.
MIN_KEYWORD_LENGTH = 2
MAX_KEYWORD_LENGTH = 120

#: Most places one search may name. "All Bangladesh" is an empty list, not 64.
MAX_LOCATIONS_PER_SEARCH = 50

#: Most leads one save or export request may name.
MAX_LEADS_PER_REQUEST = 500

#: Most rows one export file may hold.
MAX_EXPORT_ROWS = 5000


# ----------------------------------------------------------------- catalog


class CategorySchema(BaseModel):
    """A preset business category."""

    key: str
    label: str
    keyword: str


class AreaUpazilaSchema(BaseModel):
    """An upazila (or city corporation) with suggested areas."""

    code: str
    name: str
    areas: List[str] = Field(default_factory=list)


class DistrictSchema(BaseModel):
    """A district and its upazilas."""

    code: str
    name: str
    upazilas: List[AreaUpazilaSchema]


class DivisionSchema(BaseModel):
    """A division and its districts."""

    code: str
    name: str
    districts: List[DistrictSchema]


class CatalogSchema(BaseModel):
    """Everything the search form needs: categories and the location tree."""

    categories: List[CategorySchema]
    divisions: List[DivisionSchema]
    places_configured: bool


# ---------------------------------------------------------------- searches


class LocationSelectionSchema(BaseModel):
    """One selected place. Codes from the catalog; ``area`` is free text."""

    model_config = ConfigDict(str_strip_whitespace=True)

    division: Optional[str] = Field(default=None, max_length=60)
    district: Optional[str] = Field(default=None, max_length=60)
    upazila: Optional[str] = Field(default=None, max_length=60)
    area: Optional[str] = Field(default=None, max_length=80)

    @field_validator("division", "district", "upazila", "area")
    @classmethod
    def blank_to_none(cls, value: Optional[str]) -> Optional[str]:
        """An untouched select arrives as ``""``."""
        return value or None


class StartSearchSchema(BaseModel):
    """Start a business search."""

    model_config = ConfigDict(str_strip_whitespace=True)

    keyword: str = Field(min_length=MIN_KEYWORD_LENGTH, max_length=MAX_KEYWORD_LENGTH)
    category: Optional[str] = Field(default=None, max_length=60)
    #: Empty = all of Bangladesh.
    locations: List[LocationSelectionSchema] = Field(
        default_factory=list, max_length=MAX_LOCATIONS_PER_SEARCH
    )

    @field_validator("keyword")
    @classmethod
    def clean_keyword(cls, value: str) -> str:
        """Collapse whitespace; refuse control characters."""
        value = " ".join(value.split())
        if any(ord(ch) < 32 for ch in value):
            raise ValueError("Keyword contains invalid characters")
        if len(value) < MIN_KEYWORD_LENGTH:
            raise ValueError(
                f"Keyword must be at least {MIN_KEYWORD_LENGTH} characters"
            )
        return value


class SearchLocationSchema(BaseModel):
    """A place as stored on a search."""

    code: str
    label: str
    level: str
    selection: Dict[str, Optional[str]] = Field(default_factory=dict)


class SearchSchema(BaseModel):
    """A search, with its progress and summary counts."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    keyword: str
    category: Optional[str] = None
    locations: List[SearchLocationSchema]
    location_label: str
    status: SearchStatus
    total_targets: int
    completed_targets: int
    failed_targets: int
    api_requests: int
    total_results: int
    leads_found: int
    with_phone: int
    without_website: int
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def progress_percent(self) -> int:
        """Share of targets done, 0-100."""
        if self.status.is_finished:
            return 100
        if not self.total_targets:
            return 0
        done = self.completed_targets + self.failed_targets
        return min(99, round(100 * done / self.total_targets))


# ------------------------------------------------------------------- leads


class LeadSchema(BaseModel):
    """A business as a lead list shows it.

    Every Google field is nullable: Google omits what a business has not
    published, and ``content_expired`` leads have had theirs purged.
    """

    id: UUID
    place_id: str
    name: Optional[str] = None
    category: Optional[str] = None
    types: List[str] = Field(default_factory=list)
    rating: Optional[float] = None
    review_count: Optional[int] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    phone_international: Optional[str] = None
    phone_normalized: Optional[str] = None
    website: Optional[str] = None
    google_maps_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    opening_hours: List[str] = Field(default_factory=list)
    business_status: Optional[str] = None
    division: Optional[str] = None
    district: Optional[str] = None
    upazila: Optional[str] = None
    area: Optional[str] = None
    has_website: bool
    has_phone: bool
    is_potential_lead: bool
    is_duplicate_phone: bool = False
    saved_lead_id: Optional[UUID] = None
    saved_status: Optional[LeadStatus] = None
    content_expired: bool = False
    fetched_at: Optional[datetime] = None


class LeadSummarySchema(BaseModel):
    """Counts and filter options over a lead list's scope."""

    total: int
    without_website: int
    with_phone: int
    potential: int
    duplicate_phones: int
    divisions: List[str]
    districts: List[str]
    categories: List[str]


class SaveLeadsSchema(BaseModel):
    """Save one or many leads."""

    lead_ids: List[UUID] = Field(min_length=1, max_length=MAX_LEADS_PER_REQUEST)
    search_id: Optional[UUID] = None
    status: LeadStatus = LeadStatus.NEW


class SaveLeadsResultSchema(BaseModel):
    """What a save did. Already-saved leads are left as they were."""

    saved: int
    already_saved: int
    not_found: int


class LeadNoteSchema(BaseModel):
    """A note on a saved lead."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    body: str
    created_at: datetime


class LeadNoteCreateSchema(BaseModel):
    """Add a note."""

    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(min_length=1, max_length=2000)


class SavedLeadSchema(BaseModel):
    """A saved lead: the business, its status and the user's notes."""

    id: UUID
    status: LeadStatus
    search_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    lead: LeadSchema
    notes: List[LeadNoteSchema] = Field(default_factory=list)


class SavedLeadUpdateSchema(BaseModel):
    """Move a saved lead along the pipeline."""

    status: LeadStatus


# ----------------------------------------------------------------- exports

ExportScope = Literal["search", "leads", "saved", "selection"]
Presence = Optional[Literal["with", "without"]]


class ExportRequestSchema(BaseModel):
    """Produce an export file.

    ``scope`` picks the rows: one search's results, every lead of the user's,
    their saved leads, or an explicit selection. The filters narrow any scope
    except ``selection``.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    format: ExportFormat
    scope: ExportScope = "leads"
    search_id: Optional[UUID] = None
    lead_ids: List[UUID] = Field(default_factory=list, max_length=MAX_LEADS_PER_REQUEST)
    website: Presence = None
    phone: Presence = None
    min_rating: Optional[float] = Field(default=None, ge=0, le=5)
    min_reviews: Optional[int] = Field(default=None, ge=0)
    division: Optional[str] = Field(default=None, max_length=80)
    district: Optional[str] = Field(default=None, max_length=80)
    category: Optional[str] = Field(default=None, max_length=120)
    text: Optional[str] = Field(default=None, max_length=120)
    duplicates_only: bool = False
    #: Phone list only: one row per distinct number.
    unique_phones: bool = False

    @model_validator(mode="after")
    def check_scope(self) -> "ExportRequestSchema":
        """A search export names its search; a selection names its leads."""
        if self.scope == "search" and self.search_id is None:
            raise ValueError("search_id is required for a search export")
        if self.scope == "selection" and not self.lead_ids:
            raise ValueError("Select at least one lead to export")
        return self


class LeadExportSchema(BaseModel):
    """One export in the history."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    format: ExportFormat
    scope: str
    search_id: Optional[UUID] = None
    row_count: int
    file_name: str
    filters: Dict[str, Any]
    created_at: datetime


# ---------------------------------------------------------------- overview


class QuotaSchema(BaseModel):
    """Today's Places request allowance."""

    limit: int
    used: int
    remaining: int
    max_per_search: int
    resets_at: datetime


class OverviewStatsSchema(BaseModel):
    """The dashboard's headline numbers."""

    total_businesses: int
    without_website: int
    with_phone: int
    potential_leads: int
    saved_leads: int
    total_searches: int
    exports: int


class OverviewSchema(BaseModel):
    """The Lead Finder dashboard."""

    stats: OverviewStatsSchema
    saved_by_status: Dict[LeadStatus, int]
    quota: QuotaSchema
    recent_searches: List[SearchSchema]
    recent_leads: List[LeadSchema]
    places_configured: bool


# ------------------------------------------------------------------- admin


class LeadFinderSettingsSchema(BaseModel):
    """The admin's Lead Finder settings, with usage for context."""

    registration_enabled: bool
    daily_request_quota: int
    max_requests_per_search: int
    updated_at: datetime
    places_configured: bool
    content_ttl_days: int
    lead_finder_users: int
    searches_today: int
    requests_today: int
    leads_stored: int


class LeadFinderSettingsUpdateSchema(BaseModel):
    """A partial update of the settings."""

    registration_enabled: Optional[bool] = None
    daily_request_quota: Optional[int] = Field(default=None, ge=0, le=100000)
    max_requests_per_search: Optional[int] = Field(default=None, ge=1, le=1000)


class RegistrationStatusSchema(BaseModel):
    """Whether the Lead Finder sign-up form is open — public."""

    registration_enabled: bool
