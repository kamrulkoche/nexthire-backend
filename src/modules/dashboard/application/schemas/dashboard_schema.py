"""Dashboard schemas. Mirrored in `src/interface/seeker.interface.ts` (`ISeekerDashboard`) and `admin.interface.ts` (`IAdminDashboard`)."""

from typing import List

from pydantic import BaseModel, Field

from src.modules.collection.application.schemas.collection_run_schema import (
    CollectionRunSchema,
)
from src.modules.recommendation.application.schemas.recommendation_schema import (
    RecommendationSchema,
)
from src.modules.tracker.application.schemas.application_schema import (
    ApplicationCountsSchema,
)


class SeekerDashboardSchema(BaseModel):
    """The seeker's home screen."""

    has_preferences: bool = False
    saved_jobs: int = 0
    applications: ApplicationCountsSchema = Field(
        default_factory=ApplicationCountsSchema
    )
    strong_matches: int = Field(
        default=0, description="Undismissed matches scoring 70+"
    )
    unread_notifications: int = 0
    new_jobs_this_week: int = 0
    top_matches: List[RecommendationSchema] = Field(default_factory=list)
    unavailable: List[str] = Field(
        default_factory=list,
        description="Panels that could not be read; the rest still render",
    )


class AdminJobCountsSchema(BaseModel):
    """Job totals by state."""

    total: int = 0
    visible: int = 0
    hidden: int = 0
    stale: int = 0
    duplicates: int = 0


class AdminDashboardSchema(BaseModel):
    """The admin home screen."""

    jobs: AdminJobCountsSchema = Field(default_factory=AdminJobCountsSchema)
    sources_total: int = 0
    sources_enabled: int = 0
    runs_last_24h: dict[str, int] = Field(default_factory=dict)
    seekers: int = 0
    admins: int = 0
    recent_runs: List[CollectionRunSchema] = Field(default_factory=list)
    unavailable: List[str] = Field(default_factory=list)
