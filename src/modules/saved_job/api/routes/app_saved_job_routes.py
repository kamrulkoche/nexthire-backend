"""
Saved jobs — the seeker's bookmarks. Mounted at `/app/saved-jobs`.

Any signed-in user, acting on their OWN bookmarks: the user comes from the
session, and the path carries only the job's id. Save is a PUT because it is
idempotent — saving twice leaves one bookmark.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import SIGNED_IN, hasAccess
from src.shared.application.schemas.pagination import (
    ListQueryParams,
    PaginatedResponseSchema,
    list_query_params,
)

from ...application.schemas.saved_job_schema import SavedJobSchema, SaveJobSchema
from ...application.use_cases.saved_job_use_cases import (
    ListSavedJobsUseCase,
    SaveJobUseCase,
    UnsaveJobUseCase,
)
from ..dependencies import (
    get_list_saved_jobs_use_case,
    get_save_job_use_case,
    get_unsave_job_use_case,
)

router = APIRouter(tags=["Saved Jobs"])


@router.get("", response_model=PaginatedResponseSchema[SavedJobSchema])
async def list_saved_jobs(
    params: ListQueryParams = Depends(list_query_params),
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: ListSavedJobsUseCase = Depends(get_list_saved_jobs_use_case),
):
    """
    List the caller's saved jobs, newest first.

    **Access:** Any signed-in user, own bookmarks only. A job that has since
    been removed stays listed with `job.is_available: false`.
    """
    assert current_user.id is not None
    items, total = await use_case.execute(current_user.id, params)
    return PaginatedResponseSchema.build(items, total, params)


@router.put("/{job_id}", response_model=SavedJobSchema)
async def save_job(
    job_id: UUID,
    payload: SaveJobSchema,
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: SaveJobUseCase = Depends(get_save_job_use_case),
):
    """
    Save a job, or change the note on a saved one.

    **Access:** Any signed-in user

    **Errors:**
    - 404 if the job does not exist or is not visible
    """
    assert current_user.id is not None
    return await use_case.execute(current_user.id, job_id, payload)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unsave_job(
    job_id: UUID,
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: UnsaveJobUseCase = Depends(get_unsave_job_use_case),
):
    """
    Remove a saved job.

    **Access:** Any signed-in user, own bookmarks only

    **Errors:**
    - 404 if the caller had not saved this job
    """
    assert current_user.id is not None
    await use_case.execute(current_user.id, job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
