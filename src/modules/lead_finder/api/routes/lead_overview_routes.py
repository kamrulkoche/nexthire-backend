"""
The Lead Finder dashboard (`/lead/overview`) and the search form's catalog
(`/lead/catalog`). Lead finders only.
"""

from fastapi import APIRouter, Depends

from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import LEAD_FINDER_ONLY, hasAccess

from ...application.schemas.lead_finder_schema import CatalogSchema, OverviewSchema
from ...application.use_cases.lead_use_cases import GetCatalogUseCase, OverviewUseCase
from ..dependencies import get_catalog_use_case, get_overview_use_case

overview_router = APIRouter(tags=["Lead Finder Overview"])
catalog_router = APIRouter(tags=["Lead Finder Overview"])


@overview_router.get("", response_model=OverviewSchema)
async def get_overview(
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: OverviewUseCase = Depends(get_overview_use_case),
):
    """Headline counts, today's quota, recent searches and recent leads."""
    assert current_user.id is not None
    return await use_case.execute(current_user.id)


@catalog_router.get("", response_model=CatalogSchema)
async def get_catalog(
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: GetCatalogUseCase = Depends(get_catalog_use_case),
):
    """
    Preset categories and Bangladesh's location tree (8 divisions, 64
    districts, their upazilas, suggested areas), and whether a Google Maps key
    is configured.
    """
    return await use_case.execute()
