"""Dashboard use cases — read-only counts across modules, no collections of their own.

As in hgs-backend's dashboard, each panel is read separately and a failing one
is reported in ``unavailable`` rather than failing the whole screen.
"""

from datetime import timedelta
from uuid import UUID

from src.modules.collection.application.use_cases.run_history_use_cases import (
    present_runs,
)
from src.modules.collection.infrastructure.repositories.collection_run_repository import (
    CollectionRunRepository,
)
from src.modules.job.infrastructure.repositories.job_repository import JobRepository
from src.modules.job_source.infrastructure.repositories.job_source_repository import (
    JobSourceRepository,
)
from src.modules.notification.infrastructure.repositories.notification_repository import (
    NotificationRepository,
)
from src.modules.preference.infrastructure.repositories.preference_repository import (
    PreferenceRepository,
)
from src.modules.recommendation.application.use_cases.recommendation_use_cases import (
    ListRecommendationsUseCase,
)
from src.modules.recommendation.infrastructure.repositories.job_match_repository import (
    JobMatchRepository,
)
from src.modules.saved_job.infrastructure.repositories.saved_job_repository import (
    SavedJobRepository,
)
from src.modules.tracker.application.use_cases.application_use_cases import (
    ApplicationCountsUseCase,
)
from src.modules.user.domain.enums.user_role import UserRole
from src.modules.user.infrastructure.repositories.user_repository import UserRepository
from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.time import utc_now
from src.shared.infrastructure.database import MongoSession
from src.shared.infrastructure.logging import get_logger
from src.shared.utils.config import settings

from ..schemas.dashboard_schema import (
    AdminDashboardSchema,
    AdminJobCountsSchema,
    SeekerDashboardSchema,
)

logger = get_logger(__name__)

TOP_MATCHES = 5
RECENT_RUNS = 8


class GetSeekerDashboardUseCase:
    """The seeker's home screen."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.session = session

    async def execute(self, user_id: UUID) -> SeekerDashboardSchema:
        """Read every panel; report the ones that fail instead of failing."""
        result = SeekerDashboardSchema()
        panels = {
            "preferences": self._preferences,
            "saved_jobs": self._saved,
            "applications": self._applications,
            "matches": self._matches,
            "notifications": self._notifications,
            "new_jobs": self._new_jobs,
        }
        for name, read in panels.items():
            try:
                await read(user_id, result)
            except Exception as e:
                logger.error(f"Dashboard panel '{name}' failed: {e}")
                self.session.rollback()
                result.unavailable.append(name)
        return result

    async def _preferences(self, user_id: UUID, out: SeekerDashboardSchema) -> None:
        out.has_preferences = (
            await PreferenceRepository(self.session).get_for_user(user_id)
        ) is not None

    async def _saved(self, user_id: UUID, out: SeekerDashboardSchema) -> None:
        out.saved_jobs = await SavedJobRepository(self.session).count_for_user(user_id)

    async def _applications(self, user_id: UUID, out: SeekerDashboardSchema) -> None:
        out.applications = await ApplicationCountsUseCase(self.session).execute(user_id)

    async def _matches(self, user_id: UUID, out: SeekerDashboardSchema) -> None:
        out.strong_matches = await JobMatchRepository(self.session).count_strong(
            user_id, settings.recommendation_notify_score
        )
        out.top_matches, _ = await ListRecommendationsUseCase(self.session).execute(
            user_id, ListQueryParams(page=1, page_size=TOP_MATCHES)
        )

    async def _notifications(self, user_id: UUID, out: SeekerDashboardSchema) -> None:
        out.unread_notifications = await NotificationRepository(
            self.session
        ).unread_count(user_id)

    async def _new_jobs(self, user_id: UUID, out: SeekerDashboardSchema) -> None:
        out.new_jobs_this_week = await JobRepository(self.session).visible_count(
            since=utc_now() - timedelta(days=7)
        )


class GetAdminDashboardUseCase:
    """The admin home screen."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.session = session

    async def execute(self) -> AdminDashboardSchema:
        """Read every panel; report the ones that fail instead of failing."""
        result = AdminDashboardSchema()
        panels = {
            "jobs": self._jobs,
            "sources": self._sources,
            "runs": self._runs,
            "users": self._users,
        }
        for name, read in panels.items():
            try:
                await read(result)
            except Exception as e:
                logger.error(f"Admin dashboard panel '{name}' failed: {e}")
                self.session.rollback()
                result.unavailable.append(name)
        return result

    async def _jobs(self, out: AdminDashboardSchema) -> None:
        counts = await JobRepository(self.session).moderation_counts()
        out.jobs = AdminJobCountsSchema(**counts)

    async def _sources(self, out: AdminDashboardSchema) -> None:
        out.sources_total, out.sources_enabled = await JobSourceRepository(
            self.session
        ).counts()

    async def _runs(self, out: AdminDashboardSchema) -> None:
        runs = CollectionRunRepository(self.session)
        out.runs_last_24h = await runs.counts_since(utc_now() - timedelta(hours=24))
        out.recent_runs = present_runs(self.session, await runs.recent(RECENT_RUNS))

    async def _users(self, out: AdminDashboardSchema) -> None:
        counts = await UserRepository(self.session).counts_by_role()
        out.seekers = counts.get(UserRole.SEEKER.value, 0)
        out.admins = counts.get(UserRole.ADMIN.value, 0)
