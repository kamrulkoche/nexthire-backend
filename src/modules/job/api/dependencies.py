"""Job module dependencies for dependency injection."""

from typing import Optional
from uuid import UUID

from fastapi import Depends, Query
from src.shared.infrastructure.database import MongoSession

from src.shared.infrastructure.database import get_db

from ..application.use_cases.job_use_cases import (
    AdminListJobsUseCase,
    GetJobUseCase,
    ModerateJobUseCase,
    PublicStatsUseCase,
    SearchJobsUseCase,
)
from ..domain.enums.employment_type import EmploymentType
from ..infrastructure.repositories.job_repository import JobSearchFilters


def job_search_filters(
    location: Optional[str] = Query(default=None, max_length=100),
    remote: Optional[bool] = Query(default=None, description="true = remote only"),
    employment_type: Optional[EmploymentType] = Query(default=None),
    posted_within_days: Optional[int] = Query(default=None, ge=1, le=365),
    salary_min: Optional[int] = Query(default=None, ge=0),
    source_id: Optional[UUID] = Query(default=None),
) -> JobSearchFilters:
    """The Job Search screen's filters, from the query string."""
    return JobSearchFilters(
        location=location or None,
        remote=remote,
        employment_type=employment_type,
        posted_within_days=posted_within_days,
        salary_min=salary_min,
        source_id=source_id,
    )


def get_search_jobs_use_case(db: MongoSession = Depends(get_db)) -> SearchJobsUseCase:
    """Get the search use case with the shared DB session."""
    return SearchJobsUseCase(db)


def get_get_job_use_case(db: MongoSession = Depends(get_db)) -> GetJobUseCase:
    """Get the job detail use case with the shared DB session."""
    return GetJobUseCase(db)


def get_admin_list_jobs_use_case(
    db: MongoSession = Depends(get_db),
) -> AdminListJobsUseCase:
    """Get the moderation list use case with the shared DB session."""
    return AdminListJobsUseCase(db)


def get_moderate_job_use_case(db: MongoSession = Depends(get_db)) -> ModerateJobUseCase:
    """Get the moderation use case with the shared DB session."""
    return ModerateJobUseCase(db)


def get_public_stats_use_case(db: MongoSession = Depends(get_db)) -> PublicStatsUseCase:
    """Get the landing stats use case with the shared DB session."""
    return PublicStatsUseCase(db)
