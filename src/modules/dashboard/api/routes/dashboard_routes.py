"""
Dashboards. Two routers, one per family, mounted at `/app/dashboard` and
`/admin/dashboard` — authentication is a property of the file a route is in,
so the two live apart even though they are one module.
"""

from fastapi import APIRouter, Depends

from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import ADMIN_ONLY, SIGNED_IN, hasAccess

from ...application.schemas.dashboard_schema import (
    AdminDashboardSchema,
    SeekerDashboardSchema,
)
from ...application.use_cases.dashboard_use_cases import (
    GetAdminDashboardUseCase,
    GetSeekerDashboardUseCase,
)
from ..dependencies import get_admin_dashboard_use_case, get_seeker_dashboard_use_case

app_router = APIRouter(tags=["Dashboard"])
admin_router = APIRouter(tags=["Admin Dashboard"])


@app_router.get("", response_model=SeekerDashboardSchema)
async def seeker_dashboard(
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: GetSeekerDashboardUseCase = Depends(get_seeker_dashboard_use_case),
):
    """
    The caller's dashboard: saved jobs, applications, matches, notifications.

    **Access:** Any signed-in user. A panel that could not be read is named in
    `unavailable`; the others still come back.
    """
    assert current_user.id is not None
    return await use_case.execute(current_user.id)


@admin_router.get("", response_model=AdminDashboardSchema)
async def admin_dashboard(
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: GetAdminDashboardUseCase = Depends(get_admin_dashboard_use_case),
):
    """
    Jobs, sources, recent runs and user counts.

    **Access:** Admin only
    """
    return await use_case.execute()
