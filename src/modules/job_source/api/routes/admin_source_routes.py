"""
Job sources — mounted at `/admin/sources`. Admin only.

To collect from a source now, `POST /admin/runs` with its id.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import ADMIN_ONLY, hasAccess
from src.shared.application.schemas.pagination import (
    ListQueryParams,
    PaginatedResponseSchema,
    list_query_params,
)

from ...application.schemas.job_source_schema import (
    JobSourceAdminSchema,
    JobSourceCreateSchema,
    JobSourceUpdateSchema,
)
from ...application.use_cases.job_source_use_cases import (
    CreateSourceUseCase,
    DeleteSourceUseCase,
    GetSourceUseCase,
    ListSourcesUseCase,
    UpdateSourceUseCase,
)
from ...domain.enums.source_type import SourceType
from ..dependencies import (
    get_create_source_use_case,
    get_delete_source_use_case,
    get_get_source_use_case,
    get_list_sources_use_case,
    get_update_source_use_case,
)

router = APIRouter(tags=["Admin Sources"])


@router.get("", response_model=PaginatedResponseSchema[JobSourceAdminSchema])
async def list_sources(
    source_type: Optional[SourceType] = Query(default=None),
    enabled: Optional[bool] = Query(default=None),
    params: ListQueryParams = Depends(list_query_params),
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: ListSourcesUseCase = Depends(get_list_sources_use_case),
):
    """
    List job sources with their live job counts.

    **Access:** Admin only

    Searchable over name and slug. Sort by `name`, `source_type`,
    `last_run_at`, `next_run_at` or `created_at`.
    """
    items, total = await use_case.execute(
        params, source_type=source_type, enabled=enabled
    )
    return PaginatedResponseSchema.build(items, total, params)


@router.post(
    "", response_model=JobSourceAdminSchema, status_code=status.HTTP_201_CREATED
)
async def create_source(
    payload: JobSourceCreateSchema,
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: CreateSourceUseCase = Depends(get_create_source_use_case),
):
    """
    Add a job source. It is due at once.

    **Access:** Admin only

    **Errors:**
    - 409 if the slug is taken
    - 422 if the config breaks the type's rules (unknown key, missing URL, ...)
    """
    return await use_case.execute(payload, current_user.id)


@router.get("/{source_id}", response_model=JobSourceAdminSchema)
async def get_source(
    source_id: UUID,
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: GetSourceUseCase = Depends(get_get_source_use_case),
):
    """
    Read one job source.

    **Access:** Admin only
    """
    return await use_case.execute(source_id)


@router.patch("/{source_id}", response_model=JobSourceAdminSchema)
async def update_source(
    source_id: UUID,
    payload: JobSourceUpdateSchema,
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: UpdateSourceUseCase = Depends(get_update_source_use_case),
):
    """
    Edit a source's name, config, schedule, or pause / resume it.

    **Access:** Admin only

    **Errors:**
    - 404 if no live source has this id
    - 422 if the config breaks the type's rules
    """
    return await use_case.execute(source_id, payload, current_user.id)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: UUID,
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: DeleteSourceUseCase = Depends(get_delete_source_use_case),
):
    """
    Remove a source (a soft delete; it also stops collecting).

    **Access:** Admin only. Its jobs stay until they go stale.
    """
    await use_case.execute(source_id, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
