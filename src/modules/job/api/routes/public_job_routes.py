"""
Public job stats — mounted at `/public/stats`. Anonymous.

The landing page's live numbers, and the only thing this service tells someone
who is not signed in. Counts only — no job, company or source names.
"""

from fastapi import APIRouter, Depends

from ...application.schemas.job_schema import PublicStatsSchema
from ...application.use_cases.job_use_cases import PublicStatsUseCase
from ..dependencies import get_public_stats_use_case

router = APIRouter(tags=["Public"])


@router.get("", response_model=PublicStatsSchema)
async def public_stats(
    use_case: PublicStatsUseCase = Depends(get_public_stats_use_case),
):
    """
    Live counts for the landing page.

    **Access:** Public
    """
    return await use_case.execute()
