"""
AI recommendations — mounted at `/app/recommendations`. The caller's own.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import SIGNED_IN, hasAccess
from src.shared.application.schemas.pagination import (
    ListQueryParams,
    PaginatedResponseSchema,
    list_query_params,
)
from src.shared.infrastructure.security.rate_limiter import (
    enforce,
    recommendation_limiter,
)

from ...application.schemas.recommendation_schema import (
    DismissSchema,
    RecommendationSchema,
    RefreshResultSchema,
)
from ...application.use_cases.recommendation_use_cases import (
    DismissRecommendationUseCase,
    ListRecommendationsUseCase,
    RefreshRecommendationsUseCase,
)
from ..dependencies import (
    get_dismiss_recommendation_use_case,
    get_list_recommendations_use_case,
    get_refresh_recommendations_use_case,
)

router = APIRouter(tags=["Recommendations"])


@router.get("", response_model=PaginatedResponseSchema[RecommendationSchema])
async def list_recommendations(
    min_score: int = Query(default=0, ge=0, le=100, description="Lowest score shown"),
    include_dismissed: bool = Query(default=False),
    params: ListQueryParams = Depends(list_query_params),
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: ListRecommendationsUseCase = Depends(get_list_recommendations_use_case),
):
    """
    List the caller's job matches, best first.

    **Access:** Any signed-in user. Only jobs still visible are listed.
    """
    assert current_user.id is not None
    items, total = await use_case.execute(
        current_user.id,
        params,
        min_score=min_score,
        include_dismissed=include_dismissed,
    )
    return PaginatedResponseSchema.build(items, total, params)


@router.post("/refresh", response_model=RefreshResultSchema)
async def refresh_recommendations(
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: RefreshRecommendationsUseCase = Depends(
        get_refresh_recommendations_use_case
    ),
):
    """
    Score the next batch of unscored jobs against the caller's preferences.

    **Access:** Any signed-in user; rate limited per user, since each refresh
    can cost a Gemini call. With no Gemini key, or if Gemini fails, the
    heuristic scorer is used and `fallback_reason` says so.

    **Errors:**
    - 422 if the caller has not saved preferences yet
    - 429 when the hourly refresh budget is spent
    """
    assert current_user.id is not None
    enforce(recommendation_limiter, f"user:{current_user.id}")
    return await use_case.execute(current_user.id)


@router.put("/{job_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_recommendation(
    job_id: UUID,
    payload: DismissSchema,
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: DismissRecommendationUseCase = Depends(
        get_dismiss_recommendation_use_case
    ),
):
    """
    Hide a match from recommendations (`dismissed: true`) or restore it.

    **Access:** Any signed-in user, own matches only

    **Errors:**
    - 404 if the caller has no match for this job
    """
    assert current_user.id is not None
    await use_case.execute(current_user.id, job_id, payload.dismissed)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
