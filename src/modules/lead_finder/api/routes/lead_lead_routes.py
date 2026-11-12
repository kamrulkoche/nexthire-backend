"""
Leads — mounted at `/lead/leads`. Lead finders only, own scope only.

A lead is readable when one of the caller's searches found it or they saved it.
`GET` takes the shared list contract (`page`, `page_size`, `search`, `sort`,
`order`) plus the lead filters below, which combine with AND.
"""

from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import LEAD_FINDER_ONLY, hasAccess
from src.shared.application.schemas.pagination import (
    ListQueryParams,
    PaginatedResponseSchema,
    list_query_params,
)
from src.shared.infrastructure.security.rate_limiter import (
    enforce,
    lead_refresh_limiter,
)

from ...application.schemas.lead_finder_schema import LeadSchema, LeadSummarySchema
from ...application.use_cases.lead_use_cases import (
    GetLeadUseCase,
    LeadSummaryUseCase,
    ListLeadsUseCase,
    RefreshLeadUseCase,
)
from ...domain.value_objects.lead_filter import LeadFilter
from ..dependencies import (
    get_get_lead_use_case,
    get_lead_summary_use_case,
    get_list_leads_use_case,
    get_refresh_lead_use_case,
)

router = APIRouter(tags=["Lead Finder Leads"])

PresenceQuery = Optional[Literal["with", "without"]]


def lead_filter(
    search_id: Optional[UUID] = Query(default=None, description="One search's results"),
    preset: Optional[Literal["potential", "all"]] = Query(
        default=None,
        description="`potential` = no website AND a phone number. Overrides "
        "`website` and `phone`.",
    ),
    website: PresenceQuery = Query(default=None, description="with | without"),
    phone: PresenceQuery = Query(default=None, description="with | without"),
    min_rating: Optional[float] = Query(default=None, ge=0, le=5),
    min_reviews: Optional[int] = Query(default=None, ge=0),
    division: Optional[str] = Query(default=None, max_length=80),
    district: Optional[str] = Query(default=None, max_length=80),
    category: Optional[str] = Query(default=None, max_length=120),
    saved: Optional[bool] = Query(
        default=None, description="Only saved / only unsaved"
    ),
    duplicates: bool = Query(default=False, description="Only shared phone numbers"),
    params: ListQueryParams = Depends(list_query_params),
) -> LeadFilter:
    """The lead filters from the query string."""
    if preset == "potential":
        website, phone = "without", "with"
    return LeadFilter(
        search_id=search_id,
        website=website,
        phone=phone,
        min_rating=min_rating,
        min_reviews=min_reviews,
        division=division or None,
        district=district or None,
        category=category or None,
        text=params.normalized_search,
        saved=saved,
        duplicate_phone_only=duplicates,
    )


@router.get("", response_model=PaginatedResponseSchema[LeadSchema])
async def list_leads(
    filters: LeadFilter = Depends(lead_filter),
    params: ListQueryParams = Depends(list_query_params),
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: ListLeadsUseCase = Depends(get_list_leads_use_case),
):
    """
    The caller's leads, filtered.

    Sort by `relevance` (default: potential leads first, then Google's order),
    `name`, `rating`, `review_count` or `district`. `search` matches name,
    address and phone.

    **Errors:** 404 if `search_id` is not the caller's search.
    """
    assert current_user.id is not None
    items, total = await use_case.execute(
        current_user.id,
        filters,
        offset=params.offset,
        limit=params.limit,
        sort=params.sort,
        order=params.order,
    )
    return PaginatedResponseSchema.build(items, total, params)


@router.get("/summary", response_model=LeadSummarySchema)
async def lead_summary(
    search_id: Optional[UUID] = Query(default=None),
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: LeadSummaryUseCase = Depends(get_lead_summary_use_case),
):
    """Counts and filter options (districts, categories) for the scope."""
    assert current_user.id is not None
    return await use_case.execute(current_user.id, search_id)


@router.get("/{lead_id}", response_model=LeadSchema)
async def get_lead(
    lead_id: UUID,
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: GetLeadUseCase = Depends(get_get_lead_use_case),
):
    """One lead. **Errors:** 404 if outside the caller's scope."""
    assert current_user.id is not None
    return await use_case.execute(current_user.id, lead_id)


@router.post("/{lead_id}/refresh", response_model=LeadSchema)
async def refresh_lead(
    lead_id: UUID,
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: RefreshLeadUseCase = Depends(get_refresh_lead_use_case),
):
    """
    Re-read the lead's details from Google (Place Details).

    **Errors:** 404 if outside the caller's scope or gone from Google; 429
    after 60 refreshes an hour; 502 when Google refuses.
    """
    enforce(lead_refresh_limiter, f"user:{current_user.id}")
    assert current_user.id is not None
    return await use_case.execute(current_user.id, lead_id)
