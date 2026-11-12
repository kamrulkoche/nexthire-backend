"""Use cases behind the application tracker.

Every method takes the caller's id from the session. A row id from the path is
only ever looked up together with that user id, so another seeker's row is a
404, not a 403 — its existence is not the caller's business.
"""

from typing import List, Optional, Sequence, Tuple
from uuid import UUID

from src.shared.infrastructure.database import MongoSession

from src.modules.job.application.services.job_presenter import is_available
from src.modules.job.infrastructure.repositories.job_repository import JobRepository
from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.already_exists_error import AlreadyExistsError
from src.shared.domain.exceptions.not_found_error import NotFoundError
from src.shared.domain.time import utc_now

from ...domain.entities.job_application import JobApplication
from ...domain.enums.application_status import ApplicationStatus
from ...infrastructure.repositories.application_repository import ApplicationRepository
from ..schemas.application_schema import (
    ApplicationCountsSchema,
    ApplicationCreateSchema,
    ApplicationSchema,
    ApplicationUpdateSchema,
)


class _ApplicationUseCase:
    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.session = session
        self.repository = ApplicationRepository(session)
        self.jobs = JobRepository(session)

    async def _present(self, rows: Sequence[JobApplication]) -> List[ApplicationSchema]:
        jobs = await self.jobs.get_many(row.job_id for row in rows if row.job_id)
        return [
            ApplicationSchema.model_validate(row).model_copy(
                update={
                    "job_available": bool(
                        row.job_id
                        and row.job_id in jobs
                        and is_available(jobs[row.job_id])
                    )
                }
            )
            for row in rows
        ]

    async def _load(self, user_id: UUID, application_id: UUID) -> JobApplication:
        row = await self.repository.get_for_user(user_id, application_id)
        if row is None:
            raise NotFoundError(entity_name="JobApplication", entity_id=application_id)
        return row


class ListApplicationsUseCase(_ApplicationUseCase):
    """The caller's tracker."""

    async def execute(
        self,
        user_id: UUID,
        params: ListQueryParams,
        *,
        status: Optional[ApplicationStatus] = None,
    ) -> Tuple[List[ApplicationSchema], int]:
        """List applications, most recently changed first by default."""
        rows, total = await self.repository.list_for_user(
            user_id, params, status=status
        )
        return await self._present(rows), total


class ApplicationCountsUseCase(_ApplicationUseCase):
    """Per-status totals."""

    async def execute(self, user_id: UUID) -> ApplicationCountsSchema:
        """Count the caller's applications per status."""
        counts = await self.repository.counts_by_status(user_id)
        known = {s.value: counts.get(s.value, 0) for s in ApplicationStatus}
        return ApplicationCountsSchema(**known, total=sum(known.values()))


class GetApplicationUseCase(_ApplicationUseCase):
    """Read one application."""

    async def execute(self, user_id: UUID, application_id: UUID) -> ApplicationSchema:
        """Read one of the caller's applications.

        Raises:
            NotFoundError: If the caller has no such application
        """
        return (await self._present([await self._load(user_id, application_id)]))[0]


class CreateApplicationUseCase(_ApplicationUseCase):
    """Start tracking an application."""

    async def execute(
        self, user_id: UUID, payload: ApplicationCreateSchema
    ) -> ApplicationSchema:
        """Create a tracker row, copying the job's details when one is given.

        Raises:
            NotFoundError: ``job_id`` names a job the seeker cannot see
            AlreadyExistsError: The seeker already tracks this job — one row
                per job, so the tracker never shows the same role twice
        """
        title, company = payload.title, payload.company
        location = payload.location
        url = str(payload.url) if payload.url else None

        if payload.job_id is not None:
            job = await self.jobs.get_visible(payload.job_id)
            if job is None:
                raise NotFoundError(entity_name="Job", entity_id=payload.job_id)
            if await self.repository.find_for_job(user_id, payload.job_id):
                raise AlreadyExistsError(
                    entity_name="JobApplication", field="job_id", value=payload.job_id
                )
            # The snapshot. Explicit values from the form win over the job's.
            title = title or job.title
            company = company or job.company
            location = location or job.location
            url = url or job.url

        now = utc_now()
        row = JobApplication(
            user_id=user_id,
            job_id=payload.job_id,
            title=title or "",
            company=company or "",
            location=location,
            url=url,
            status=payload.status,
            applied_on=payload.applied_on
            or (now.date() if payload.status == ApplicationStatus.APPLIED else None),
            next_step=payload.next_step,
            next_step_at=payload.next_step_at,
            notes=payload.notes,
            status_changed_at=now,
            created_by=user_id,
            updated_by=user_id,
        )
        created = await self.repository.create(row)
        return (await self._present([created]))[0]


class UpdateApplicationUseCase(_ApplicationUseCase):
    """Edit an application or move it along."""

    async def execute(
        self, user_id: UUID, application_id: UUID, payload: ApplicationUpdateSchema
    ) -> ApplicationSchema:
        """Apply the fields that were sent.

        Moving to ``applied`` with no ``applied_on`` fills in today, because
        that is nearly always what happened.

        Raises:
            NotFoundError: If the caller has no such application
        """
        row = await self._load(user_id, application_id)
        changes = payload.model_dump(exclude_unset=True)
        if "url" in changes and changes["url"] is not None:
            changes["url"] = str(changes["url"])
        for required in ("title", "company", "status", "notes"):
            if required in changes and changes[required] is None:
                changes.pop(required)

        new_status = changes.get("status")
        if new_status is not None and new_status != row.status:
            row.status_changed_at = utc_now()
            if new_status == ApplicationStatus.APPLIED and not (
                changes.get("applied_on") or row.applied_on
            ):
                changes["applied_on"] = utc_now().date()

        for key, value in changes.items():
            setattr(row, key, value)
        row.updated_by = user_id
        updated = await self.repository.update(row)
        return (await self._present([updated]))[0]


class DeleteApplicationUseCase(_ApplicationUseCase):
    """Stop tracking an application."""

    async def execute(self, user_id: UUID, application_id: UUID) -> None:
        """Soft-delete the row.

        Raises:
            NotFoundError: If the caller has no such application
        """
        row = await self._load(user_id, application_id)
        row.is_active = False
        row.updated_by = user_id
        await self.repository.update(row)
