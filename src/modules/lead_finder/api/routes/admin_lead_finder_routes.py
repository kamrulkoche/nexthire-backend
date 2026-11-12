"""
Lead Finder administration — mounted at `/admin/lead-finder`. Admin only.

Lead Finder ACCOUNTS are managed on the existing Users screen
(`/admin/users`, role `lead_finder`); this is the product's switches.
"""

from fastapi import APIRouter, Depends

from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import ADMIN_ONLY, hasAccess

from ...application.schemas.lead_finder_schema import (
    LeadFinderSettingsSchema,
    LeadFinderSettingsUpdateSchema,
)
from ...application.use_cases.admin_use_cases import (
    GetLeadFinderSettingsUseCase,
    UpdateLeadFinderSettingsUseCase,
)
from ..dependencies import get_lead_settings_use_case, get_update_lead_settings_use_case

router = APIRouter(tags=["Admin Lead Finder"])


@router.get("/settings", response_model=LeadFinderSettingsSchema)
async def get_settings(
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: GetLeadFinderSettingsUseCase = Depends(get_lead_settings_use_case),
):
    """Registration switch, quotas, and today's usage."""
    return await use_case.execute()


@router.patch("/settings", response_model=LeadFinderSettingsSchema)
async def update_settings(
    payload: LeadFinderSettingsUpdateSchema,
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: UpdateLeadFinderSettingsUseCase = Depends(
        get_update_lead_settings_use_case
    ),
):
    """Open or close registration; change the quotas."""
    return await use_case.execute(payload)
