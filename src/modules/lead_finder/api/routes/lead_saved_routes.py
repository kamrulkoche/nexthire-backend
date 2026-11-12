"""
Saved leads — mounted at `/lead/saved-leads`. Lead finders only, own rows only.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import LEAD_FINDER_ONLY, hasAccess
from src.shared.application.schemas.pagination import (
    ListQueryParams,
    PaginatedResponseSchema,
    list_query_params,
)

from ...application.schemas.lead_finder_schema import (
    LeadNoteCreateSchema,
    SavedLeadSchema,
    SavedLeadUpdateSchema,
    SaveLeadsResultSchema,
    SaveLeadsSchema,
)
from ...application.use_cases.saved_lead_use_cases import (
    AddLeadNoteUseCase,
    DeleteLeadNoteUseCase,
    GetSavedLeadUseCase,
    ListSavedLeadsUseCase,
    SaveLeadsUseCase,
    UnsaveLeadUseCase,
    UpdateSavedLeadUseCase,
)
from ...domain.enums import LeadStatus
from ..dependencies import (
    get_add_note_use_case,
    get_delete_note_use_case,
    get_get_saved_lead_use_case,
    get_list_saved_leads_use_case,
    get_save_leads_use_case,
    get_unsave_lead_use_case,
    get_update_saved_lead_use_case,
)

router = APIRouter(tags=["Lead Finder Saved Leads"])


@router.get("", response_model=PaginatedResponseSchema[SavedLeadSchema])
async def list_saved_leads(
    status_filter: Optional[LeadStatus] = Query(default=None, alias="status"),
    params: ListQueryParams = Depends(list_query_params),
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: ListSavedLeadsUseCase = Depends(get_list_saved_leads_use_case),
):
    """
    The caller's saved leads with notes, newest first.

    Searchable over name, address, phone and district; sort by `created_at`,
    `updated_at`, `status`, `name` or `district`.
    """
    assert current_user.id is not None
    items, total = await use_case.execute(current_user.id, params, status_filter)
    return PaginatedResponseSchema.build(items, total, params)


@router.post("", response_model=SaveLeadsResultSchema)
async def save_leads(
    payload: SaveLeadsSchema,
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: SaveLeadsUseCase = Depends(get_save_leads_use_case),
):
    """
    Save one or many leads (up to 500). Leads already saved are left as they
    are, so saving never duplicates.
    """
    assert current_user.id is not None
    return await use_case.execute(current_user.id, payload)


@router.get("/{saved_id}", response_model=SavedLeadSchema)
async def get_saved_lead(
    saved_id: UUID,
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: GetSavedLeadUseCase = Depends(get_get_saved_lead_use_case),
):
    """One saved lead. **Errors:** 404 if not the caller's."""
    assert current_user.id is not None
    return await use_case.execute(current_user.id, saved_id)


@router.patch("/{saved_id}", response_model=SavedLeadSchema)
async def update_saved_lead(
    saved_id: UUID,
    payload: SavedLeadUpdateSchema,
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: UpdateSavedLeadUseCase = Depends(get_update_saved_lead_use_case),
):
    """Change the lead status. **Errors:** 404 if not the caller's."""
    assert current_user.id is not None
    return await use_case.execute(current_user.id, saved_id, payload.status)


@router.delete("/{saved_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unsave_lead(
    saved_id: UUID,
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: UnsaveLeadUseCase = Depends(get_unsave_lead_use_case),
):
    """Unsave (its notes go too). **Errors:** 404 if not the caller's."""
    assert current_user.id is not None
    await use_case.execute(current_user.id, saved_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{saved_id}/notes",
    response_model=SavedLeadSchema,
    status_code=status.HTTP_201_CREATED,
)
async def add_note(
    saved_id: UUID,
    payload: LeadNoteCreateSchema,
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: AddLeadNoteUseCase = Depends(get_add_note_use_case),
):
    """Add a note to a saved lead. Returns the saved lead with its notes."""
    assert current_user.id is not None
    return await use_case.execute(current_user.id, saved_id, payload)


@router.delete("/{saved_id}/notes/{note_id}", response_model=SavedLeadSchema)
async def delete_note(
    saved_id: UUID,
    note_id: UUID,
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: DeleteLeadNoteUseCase = Depends(get_delete_note_use_case),
):
    """Delete a note. Returns the saved lead with its remaining notes."""
    assert current_user.id is not None
    return await use_case.execute(current_user.id, saved_id, note_id)
