"""
Application tracker — mounted at `/app/applications`. The caller's own rows.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import SIGNED_IN, hasAccess
from src.shared.application.schemas.pagination import (
    ListQueryParams,
    PaginatedResponseSchema,
    list_query_params,
)

from ...application.schemas.application_schema import (
    ApplicationCountsSchema,
    ApplicationCreateSchema,
    ApplicationSchema,
    ApplicationUpdateSchema,
)
from ...application.use_cases.application_use_cases import (
    ApplicationCountsUseCase,
    CreateApplicationUseCase,
    DeleteApplicationUseCase,
    GetApplicationUseCase,
    ListApplicationsUseCase,
    UpdateApplicationUseCase,
)
from ...domain.enums.application_status import ApplicationStatus
from ..dependencies import (
    get_application_counts_use_case,
    get_create_application_use_case,
    get_delete_application_use_case,
    get_get_application_use_case,
    get_list_applications_use_case,
    get_update_application_use_case,
)

router = APIRouter(tags=["Applications"])


@router.get("", response_model=PaginatedResponseSchema[ApplicationSchema])
async def list_applications(
    status_filter: Optional[ApplicationStatus] = Query(
        default=None, alias="status", description="Narrow to one status"
    ),
    params: ListQueryParams = Depends(list_query_params),
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: ListApplicationsUseCase = Depends(get_list_applications_use_case),
):
    """
    List the caller's tracked applications.

    **Access:** Any signed-in user

    Searchable over title, company and notes. Sort by `updated_at` (default,
    newest first), `created_at`, `applied_on`, `next_step_at`, `company` or
    `status`.
    """
    assert current_user.id is not None
    items, total = await use_case.execute(current_user.id, params, status=status_filter)
    return PaginatedResponseSchema.build(items, total, params)


@router.get("/counts", response_model=ApplicationCountsSchema)
async def application_counts(
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: ApplicationCountsUseCase = Depends(get_application_counts_use_case),
):
    """
    Count the caller's applications per status.

    **Access:** Any signed-in user. Declared before `/{application_id}`.
    """
    assert current_user.id is not None
    return await use_case.execute(current_user.id)


@router.post("", response_model=ApplicationSchema, status_code=status.HTTP_201_CREATED)
async def create_application(
    payload: ApplicationCreateSchema,
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: CreateApplicationUseCase = Depends(get_create_application_use_case),
):
    """
    Start tracking an application — from a collected job, or entered by hand.

    **Access:** Any signed-in user

    **Errors:**
    - 404 if `job_id` names a job the caller cannot see
    - 409 if the caller already tracks that job
    - 422 if neither `job_id` nor `title` + `company` is given
    """
    assert current_user.id is not None
    return await use_case.execute(current_user.id, payload)


@router.get("/{application_id}", response_model=ApplicationSchema)
async def get_application(
    application_id: UUID,
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: GetApplicationUseCase = Depends(get_get_application_use_case),
):
    """
    Read one tracked application.

    **Access:** Any signed-in user, own rows only (another seeker's id is a 404)
    """
    assert current_user.id is not None
    return await use_case.execute(current_user.id, application_id)


@router.patch("/{application_id}", response_model=ApplicationSchema)
async def update_application(
    application_id: UUID,
    payload: ApplicationUpdateSchema,
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: UpdateApplicationUseCase = Depends(get_update_application_use_case),
):
    """
    Edit a tracked application or change its status.

    **Access:** Any signed-in user, own rows only
    """
    assert current_user.id is not None
    return await use_case.execute(current_user.id, application_id, payload)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    application_id: UUID,
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: DeleteApplicationUseCase = Depends(get_delete_application_use_case),
):
    """
    Stop tracking an application (a soft delete).

    **Access:** Any signed-in user, own rows only
    """
    assert current_user.id is not None
    await use_case.execute(current_user.id, application_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
