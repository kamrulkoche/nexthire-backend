"""Main API v1 router that aggregates all module routers.

Prefixes are assigned HERE, centrally, never inside the module routers — a
module router declares only its tags and relative paths. hgs-backend and
sp-company-backend both work this way: one file is the whole URL map.

Three families of routes, and the split matters. A family is a property of the
FILE a route lives in (`app_*_routes.py`, `admin_*_routes.py`,
`public_*_routes.py`), never a flag on a decorator:

- `/api/v1/app/*` — any signed-in user (seekers, and admins using the app).
  Every per-user resource is scoped to the caller in its repository.
- `/api/v1/admin/*` — `ADMIN` only.
- `/api/v1/public/*` — anonymous; counts for the landing page.
- `/api/v1/lead/*` — `LEAD_FINDER` only: the Business Lead Finder product.
  Its users are not in `SIGNED_IN`, so they reach nothing under `/app` or
  `/admin`, and seekers and admins reach nothing here.

Plus `/api/v1/auth/*`: register and login are public and rate limited; me and
logout need a session.

A new prefix is unreachable from the browser until the frontend's matching
proxy allowlist names it (`app/api/{app,admin,public}/[...path]/route.ts`).
"""

from fastapi import APIRouter

from ...modules.auth.api.routes.auth_routes import router as auth_router
from ...modules.collection.api.routes.admin_run_routes import router as admin_run_router
from ...modules.dashboard.api.routes.dashboard_routes import (
    admin_router as admin_dashboard_router,
)
from ...modules.dashboard.api.routes.dashboard_routes import (
    app_router as app_dashboard_router,
)
from ...modules.job.api.routes.admin_job_routes import router as admin_job_router
from ...modules.job.api.routes.app_job_routes import router as app_job_router
from ...modules.job.api.routes.public_job_routes import router as public_stats_router
from ...modules.job_source.api.routes.admin_source_routes import (
    router as admin_source_router,
)
from ...modules.lead_finder.api.routes.admin_lead_finder_routes import (
    router as admin_lead_finder_router,
)
from ...modules.lead_finder.api.routes.lead_account_routes import (
    router as lead_account_router,
)
from ...modules.lead_finder.api.routes.lead_auth_routes import (
    router as lead_auth_router,
)
from ...modules.lead_finder.api.routes.lead_export_routes import (
    router as lead_export_router,
)
from ...modules.lead_finder.api.routes.lead_lead_routes import (
    router as lead_lead_router,
)
from ...modules.lead_finder.api.routes.lead_overview_routes import (
    catalog_router as lead_catalog_router,
)
from ...modules.lead_finder.api.routes.lead_overview_routes import (
    overview_router as lead_overview_router,
)
from ...modules.lead_finder.api.routes.lead_saved_routes import (
    router as lead_saved_router,
)
from ...modules.lead_finder.api.routes.lead_search_routes import (
    router as lead_search_router,
)
from ...modules.notification.api.routes.app_notification_routes import (
    router as app_notification_router,
)
from ...modules.preference.api.routes.app_preference_routes import (
    router as app_preference_router,
)
from ...modules.recommendation.api.routes.app_recommendation_routes import (
    router as app_recommendation_router,
)
from ...modules.saved_job.api.routes.app_saved_job_routes import (
    router as app_saved_job_router,
)
from ...modules.tracker.api.routes.app_tracker_routes import (
    router as app_tracker_router,
)
from ...modules.user.api.routes.account_routes import router as app_account_router
from ...modules.user.api.routes.user_routes import router as admin_user_router

api_router = APIRouter(prefix="/api/v1")

# Authentication
api_router.include_router(auth_router, prefix="/auth")
api_router.include_router(lead_auth_router, prefix="/auth/lead-finder")

# Lead Finder — LEAD_FINDER only, own rows only. Its own family (and its own
# frontend proxy, `/api/lead/*`), so it shares no route with the job finder.
api_router.include_router(lead_overview_router, prefix="/lead/overview")
api_router.include_router(lead_catalog_router, prefix="/lead/catalog")
api_router.include_router(lead_search_router, prefix="/lead/searches")
api_router.include_router(lead_lead_router, prefix="/lead/leads")
api_router.include_router(lead_saved_router, prefix="/lead/saved-leads")
api_router.include_router(lead_export_router, prefix="/lead/exports")
api_router.include_router(lead_account_router, prefix="/lead/account")

# App — any signed-in user, own rows only
api_router.include_router(app_dashboard_router, prefix="/app/dashboard")
api_router.include_router(app_job_router, prefix="/app/jobs")
api_router.include_router(app_saved_job_router, prefix="/app/saved-jobs")
api_router.include_router(app_tracker_router, prefix="/app/applications")
api_router.include_router(app_preference_router, prefix="/app/preferences")
api_router.include_router(app_recommendation_router, prefix="/app/recommendations")
api_router.include_router(app_notification_router, prefix="/app/notifications")
api_router.include_router(app_account_router, prefix="/app/account")

# Admin — ADMIN only
api_router.include_router(admin_dashboard_router, prefix="/admin/dashboard")
api_router.include_router(admin_source_router, prefix="/admin/sources")
api_router.include_router(admin_run_router, prefix="/admin/runs")
api_router.include_router(admin_job_router, prefix="/admin/jobs")
api_router.include_router(admin_user_router, prefix="/admin/users")
api_router.include_router(admin_lead_finder_router, prefix="/admin/lead-finder")

# Public — anonymous
api_router.include_router(public_stats_router, prefix="/public/stats")
