"""
Job Search and Job Details — mounted at `/app/jobs`. Any signed-in user.
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import SIGNED_IN, hasAccess
from src.shared.application.schemas.pagination import (
    ListQueryParams,
    PaginatedResponseSchema,
    list_query_params,
)

from ...application.schemas.job_schema import JobDetailSchema, JobSummarySchema
from ...application.use_cases.job_use_cases import GetJobUseCase, SearchJobsUseCase
from ...infrastructure.repositories.job_repository import JobSearchFilters
from ..dependencies import (
    get_get_job_use_case,
    get_search_jobs_use_case,
    job_search_filters,
)

router = APIRouter(tags=["Jobs"])


@router.get("", response_model=PaginatedResponseSchema[JobSummarySchema])
async def search_jobs(
    filters: JobSearchFilters = Depends(job_search_filters),
    params: ListQueryParams = Depends(list_query_params),
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: SearchJobsUseCase = Depends(get_search_jobs_use_case),
):
    """
    Search jobs.

    **Access:** Any signed-in user

    `search` matches every word against title, company and description.
    Sort by `posted_at` (default, newest first), `salary_max`, `title`,
    `company` or `last_seen_at`. Each card carries `is_saved` and the caller's
    `match_score` when one exists.
    """
    assert current_user.id is not None
    items, total = await use_case.execute(current_user.id, params, filters)
    return PaginatedResponseSchema.build(items, total, params)


@router.get("/{job_id}", response_model=JobDetailSchema)
async def get_job(
    job_id: UUID,
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: GetJobUseCase = Depends(get_get_job_use_case),
):
    """
    Read one job.

    **Access:** Any signed-in user

    **Errors:**
    - 404 if the job does not exist, or is hidden, stale or a duplicate
    """
    assert current_user.id is not None
    return await use_case.execute(current_user.id, job_id)
