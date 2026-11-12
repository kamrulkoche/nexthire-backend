"""Use cases behind Job Search, Job Details, moderation and the landing stats."""

from datetime import timedelta
from typing import List, Optional, Tuple
from uuid import UUID

from src.shared.infrastructure.database import MongoSession

from src.modules.job_source.infrastructure.repositories.job_source_repository import (
    JobSourceRepository,
)
from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.not_found_error import NotFoundError
from src.shared.domain.time import utc_now

from ...infrastructure.repositories.job_repository import (
    JobRepository,
    JobSearchFilters,
)
from ..schemas.job_schema import (
    JobAdminSchema,
    JobDetailSchema,
    JobModerationSchema,
    JobSummarySchema,
    PublicStatsSchema,
)
from ..services.job_presenter import JobPresenter


class SearchJobsUseCase:
    """Job Search."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.repository = JobRepository(session)
        self.presenter = JobPresenter(session)

    async def execute(
        self, viewer_id: UUID, params: ListQueryParams, filters: JobSearchFilters
    ) -> Tuple[List[JobSummarySchema], int]:
        """Search visible jobs, marking the caller's saves and scores."""
        rows, total = await self.repository.search(params, filters)
        return await self.presenter.summaries(rows, viewer_id), total


class GetJobUseCase:
    """Job Details."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.repository = JobRepository(session)
        self.presenter = JobPresenter(session)

    async def execute(self, viewer_id: UUID, job_id: UUID) -> JobDetailSchema:
        """Read one visible job.

        Raises:
            NotFoundError: Hidden, stale, duplicate or unknown — all one answer,
                so a seeker cannot probe which jobs an admin hid
        """
        job = await self.repository.get_visible(job_id)
        if job is None:
            raise NotFoundError(entity_name="Job", entity_id=job_id)
        return await self.presenter.detail(job, viewer_id)


class AdminListJobsUseCase:
    """The moderation list."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.repository = JobRepository(session)
        self.presenter = JobPresenter(session)

    async def execute(
        self,
        params: ListQueryParams,
        filters: JobSearchFilters,
        *,
        hidden: Optional[bool] = None,
        active: Optional[bool] = None,
    ) -> Tuple[List[JobAdminSchema], int]:
        """List every job, whatever its visibility."""
        rows, total = await self.repository.admin_list(
            params, filters, hidden=hidden, active=active
        )
        return await self.presenter.admin_rows(rows), total


class ModerateJobUseCase:
    """Hide a job from seekers, or show it again."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.repository = JobRepository(session)
        self.presenter = JobPresenter(session)

    async def execute(
        self, job_id: UUID, payload: JobModerationSchema, admin_id: Optional[UUID]
    ) -> JobAdminSchema:
        """Set ``is_hidden``. A later collection run never changes it back.

        Raises:
            NotFoundError: No job has this id
        """
        job = await self.repository.get_by_id(job_id)
        if job is None:
            raise NotFoundError(entity_name="Job", entity_id=job_id)
        job.is_hidden = payload.is_hidden
        job.updated_by = admin_id
        job = await self.repository.update(job)
        return (await self.presenter.admin_rows([job]))[0]


class PublicStatsUseCase:
    """The landing page's live counts."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.jobs = JobRepository(session)
        self.sources = JobSourceRepository(session)

    async def execute(self) -> PublicStatsSchema:
        """Count visible jobs, their companies, enabled sources and this week's arrivals."""
        _, enabled = await self.sources.counts()
        return PublicStatsSchema(
            jobs=await self.jobs.visible_count(),
            companies=await self.jobs.visible_company_count(),
            sources=enabled,
            new_this_week=await self.jobs.visible_count(
                since=utc_now() - timedelta(days=7)
            ),
        )
