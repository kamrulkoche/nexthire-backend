"""Turning Job rows into what a seeker's screen shows.

A job card carries three things the ``jobs`` table does not: the source's name,
whether the caller saved it, and the caller's match score. Every screen that
lists jobs — search, saved jobs, recommendations, the dashboard — needs the
same three, so they are added here, once, with one query each per page rather
than one per row.

This reads three other modules' repositories. hgs-backend's dashboard does the
same across its modules; it is a read-side composition, not a dependency of the
job module's own rules.
"""

from typing import Iterable, List, Optional, Sequence
from uuid import UUID

from src.shared.infrastructure.database import MongoSession

from src.modules.job_source.infrastructure.repositories.job_source_repository import (
    JobSourceRepository,
)
from src.modules.recommendation.infrastructure.repositories.job_match_repository import (
    JobMatchRepository,
)
from src.modules.saved_job.infrastructure.repositories.saved_job_repository import (
    SavedJobRepository,
)

from ...domain.entities.job import Job
from ..schemas.job_schema import JobAdminSchema, JobDetailSchema, JobSummarySchema


def is_available(job: Job) -> bool:
    """Whether a seeker could find this job in search right now."""
    return job.is_active and not job.is_hidden and job.duplicate_of_id is None


class JobPresenter:
    """Builds job schemas decorated for one viewer."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.sources = JobSourceRepository(session)
        self.saved = SavedJobRepository(session)
        self.matches = JobMatchRepository(session)

    def _source_names(self, source_ids: Iterable[UUID]) -> dict[UUID, str]:
        return {
            source_id: name
            for source_id, (name, _) in self.sources.names_for(source_ids).items()
        }

    async def summaries(
        self, jobs: Sequence[Job], viewer_id: Optional[UUID]
    ) -> List[JobSummarySchema]:
        """Cards for a list of jobs, in the order given.

        Args:
            jobs: The rows
            viewer_id: The signed-in user, or None for an anonymous read

        Returns:
            One summary per job
        """
        ids = [job.id for job in jobs if job.id is not None]
        names = self._source_names(job.source_id for job in jobs)
        saved = await self.saved.saved_job_ids(viewer_id, ids) if viewer_id else set()
        scores = await self.matches.scores_for(viewer_id, ids) if viewer_id else {}
        return [
            JobSummarySchema.model_validate(job).model_copy(
                update={
                    "source_name": names.get(job.source_id),
                    "is_saved": job.id in saved,
                    "match_score": scores.get(job.id),
                    "is_available": is_available(job),
                }
            )
            for job in jobs
        ]

    async def detail(self, job: Job, viewer_id: Optional[UUID]) -> JobDetailSchema:
        """The Job Details page for one viewer."""
        summary = (await self.summaries([job], viewer_id))[0]
        return JobDetailSchema.model_validate(job).model_copy(
            update=summary.model_dump(
                include={"source_name", "is_saved", "match_score", "is_available"}
            )
        )

    async def admin_rows(self, jobs: Sequence[Job]) -> List[JobAdminSchema]:
        """Rows for the moderation screen."""
        names = self._source_names(job.source_id for job in jobs)
        return [
            JobAdminSchema.model_validate(job).model_copy(
                update={
                    "source_name": names.get(job.source_id),
                    "is_available": is_available(job),
                }
            )
            for job in jobs
        ]
