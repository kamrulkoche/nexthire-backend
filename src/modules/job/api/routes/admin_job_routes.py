"""
Job moderation — mounted at `/admin/jobs`. Admin only.

There is no delete: a job belongs to its source, and the next run would bring
it straight back. Hiding is the moderation tool, and it sticks.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import ADMIN_ONLY, hasAccess
from src.shared.application.schemas.pagination import (
    ListQueryParams,
    PaginatedResponseSchema,
    list_query_params,
)

from ...application.schemas.job_schema import JobAdminSchema, JobModerationSchema
from ...application.use_cases.job_use_cases import (
    AdminListJobsUseCase,
    ModerateJobUseCase,
)
from ...infrastructure.repositories.job_repository import JobSearchFilters
from ..dependencies import (
    get_admin_list_jobs_use_case,
    get_moderate_job_use_case,
    job_search_filters,
)

router = APIRouter(tags=["Admin Jobs"])


@router.get("", response_model=PaginatedResponseSchema[JobAdminSchema])
async def list_jobs(
    hidden: Optional[bool] = Query(default=None, description="Only hidden / unhidden"),
    active: Optional[bool] = Query(default=None, description="Only live / stale"),
    filters: JobSearchFilters = Depends(job_search_filters),
    params: ListQueryParams = Depends(list_query_params),
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: AdminListJobsUseCase = Depends(get_admin_list_jobs_use_case),
):
    """
    List every job — hidden, stale and duplicate ones included.

    **Access:** Admin only. Same search, filters and sorts as Job Search.
    """
    items, total = await use_case.execute(params, filters, hidden=hidden, active=active)
    return PaginatedResponseSchema.build(items, total, params)


@router.patch("/{job_id}", response_model=JobAdminSchema)
async def moderate_job(
    job_id: UUID,
    payload: JobModerationSchema,
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: ModerateJobUseCase = Depends(get_moderate_job_use_case),
):
    """
    Hide a job from seekers, or show it again.

    **Access:** Admin only

    **Errors:**
    - 404 if no job has this id
    """
    return await use_case.execute(job_id, payload, current_user.id)
