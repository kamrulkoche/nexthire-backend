"""
Exports — mounted at `/lead/exports`. Lead finders only.

`POST` answers with the FILE, not JSON (CSV, XLSX or PDF), with a
`Content-Disposition: attachment` header. `ResponseWrapperMiddleware` leaves
non-JSON responses alone, and the frontend proxy streams them through.
"""

from fastapi import APIRouter, Depends, Response

from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import LEAD_FINDER_ONLY, hasAccess
from src.shared.application.schemas.pagination import (
    ListQueryParams,
    PaginatedResponseSchema,
    list_query_params,
)
from src.shared.infrastructure.security.rate_limiter import enforce, lead_export_limiter

from ...application.schemas.lead_finder_schema import (
    ExportRequestSchema,
    LeadExportSchema,
)
from ...application.use_cases.export_use_cases import (
    ExportLeadsUseCase,
    ListExportsUseCase,
)
from ..dependencies import get_export_leads_use_case, get_list_exports_use_case

router = APIRouter(tags=["Lead Finder Exports"])


@router.get("", response_model=PaginatedResponseSchema[LeadExportSchema])
async def list_exports(
    params: ListQueryParams = Depends(list_query_params),
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: ListExportsUseCase = Depends(get_list_exports_use_case),
):
    """The caller's export history, newest first."""
    assert current_user.id is not None
    items, total = await use_case.execute(current_user.id, params)
    return PaginatedResponseSchema.build(items, total, params)


@router.post(
    "",
    response_class=Response,
    responses={
        200: {
            "description": "The export file",
            "content": {
                "text/csv": {},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
                "application/pdf": {},
            },
        }
    },
)
async def export_leads(
    payload: ExportRequestSchema,
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: ExportLeadsUseCase = Depends(get_export_leads_use_case),
):
    """
    Produce an export file and record it in the history.

    **Errors:**
    - 404 if `search_id` is not the caller's
    - 422 if nothing matches, or more than 5000 rows do
    - 429 after 60 exports an hour
    """
    enforce(lead_export_limiter, f"user:{current_user.id}")
    assert current_user.id is not None
    exported = await use_case.execute(current_user.id, payload)
    return Response(
        content=exported.content,
        media_type=exported.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{exported.file_name}"',
            "X-Export-Rows": str(exported.row_count),
            "Cache-Control": "no-store",
        },
    )
