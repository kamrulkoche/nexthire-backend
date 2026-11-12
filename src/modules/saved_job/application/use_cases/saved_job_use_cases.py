"""Use cases behind Saved Jobs.

One module rather than one file per operation, as hgs-backend's `contact`
does: list, save and unsave over one table share no rule worth separating.
Every method takes the caller's id from the session, never from the request.
"""

from typing import List, Tuple
from uuid import UUID

from pymongo.errors import DuplicateKeyError
from src.shared.infrastructure.database import MongoSession

from src.modules.job.application.services.job_presenter import JobPresenter
from src.modules.job.infrastructure.repositories.job_repository import JobRepository
from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.not_found_error import NotFoundError

from ...domain.entities.saved_job import SavedJob
from ...infrastructure.repositories.saved_job_repository import SavedJobRepository
from ..schemas.saved_job_schema import SavedJobSchema, SaveJobSchema


class _SavedJobUseCase:
    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.session = session
        self.repository = SavedJobRepository(session)
        self.jobs = JobRepository(session)
        self.presenter = JobPresenter(session)

    async def _present(
        self, user_id: UUID, rows: List[SavedJob]
    ) -> List[SavedJobSchema]:
        jobs = await self.jobs.get_many(row.job_id for row in rows)
        present = [jobs[row.job_id] for row in rows if row.job_id in jobs]
        summaries = {s.id: s for s in await self.presenter.summaries(present, user_id)}
        return [
            SavedJobSchema(
                job_id=row.job_id,
                note=row.note,
                saved_at=row.created_at,
                job=summaries[row.job_id],
            )
            for row in rows
            if row.job_id in summaries
        ]


class ListSavedJobsUseCase(_SavedJobUseCase):
    """The caller's saved jobs, newest first."""

    async def execute(
        self, user_id: UUID, params: ListQueryParams
    ) -> Tuple[List[SavedJobSchema], int]:
        """List bookmarks, including ones whose job has since gone away.

        A removed job stays on this list marked ``is_available: false``: the
        seeker saved it for a reason, and silently dropping it would lose that.

        Returns:
            ``(items, total)``
        """
        rows, total = await self.repository.list_for_user(user_id, params)
        return await self._present(user_id, rows), total


class SaveJobUseCase(_SavedJobUseCase):
    """Save a job, or update the note on one already saved."""

    async def execute(
        self, user_id: UUID, job_id: UUID, payload: SaveJobSchema
    ) -> SavedJobSchema:
        """Save idempotently: a second save updates the note, never duplicates.

        Raises:
            NotFoundError: If the job is not one the seeker can see. A job
                already saved can still have its note edited after it is gone.
        """
        existing = await self.repository.get_for_user(user_id, job_id)
        if existing is None:
            if await self.jobs.get_visible(job_id) is None:
                raise NotFoundError(entity_name="Job", entity_id=job_id)
            try:
                existing = await self.repository.create(
                    SavedJob(user_id=user_id, job_id=job_id, note=payload.note)
                )
            except DuplicateKeyError:
                # A double-click raced us to the insert; the row exists now.
                existing = await self.repository.get_for_user(user_id, job_id)
                if existing is None:  # pragma: no cover - would need a delete race too
                    raise
        elif payload.note != existing.note:
            existing.note = payload.note
            self.session.add(existing)
            self.session.commit()
            self.session.refresh(existing)
        return (await self._present(user_id, [existing]))[0]


class UnsaveJobUseCase(_SavedJobUseCase):
    """Remove a bookmark."""

    async def execute(self, user_id: UUID, job_id: UUID) -> None:
        """Delete the caller's bookmark.

        Raises:
            NotFoundError: If the caller had not saved this job
        """
        if not await self.repository.delete_for_user(user_id, job_id):
            raise NotFoundError(entity_name="SavedJob", entity_id=job_id)
