"""Use cases behind the Sources screen."""

from typing import List, Optional, Sequence, Tuple
from uuid import UUID

from pymongo.errors import DuplicateKeyError
from src.shared.infrastructure.database import MongoSession

from src.modules.job.infrastructure.repositories.job_repository import JobRepository
from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.already_exists_error import AlreadyExistsError
from src.shared.domain.exceptions.not_found_error import NotFoundError
from src.shared.domain.exceptions.validation_error import ValidationError
from src.shared.domain.time import as_utc, utc_now

from ...domain.entities.job_source import JobSource
from ...domain.enums.source_type import SourceType
from ...domain.services.source_config import normalize_source_config
from ...infrastructure.repositories.job_source_repository import JobSourceRepository
from ..schemas.job_source_schema import (
    JobSourceAdminSchema,
    JobSourceCreateSchema,
    JobSourceUpdateSchema,
)


class _SourceUseCase:
    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.session = session
        self.repository = JobSourceRepository(session)
        self.jobs = JobRepository(session)

    async def _present(
        self, sources: Sequence[JobSource]
    ) -> List[JobSourceAdminSchema]:
        counts = await self.jobs.active_counts_by_source(
            s.id for s in sources if s.id is not None
        )
        now = utc_now()
        return [
            JobSourceAdminSchema.model_validate(source).model_copy(
                update={
                    "active_jobs": counts.get(source.id, 0),  # type: ignore[arg-type]
                    "is_running": bool(
                        source.locked_until and as_utc(source.locked_until) > now  # type: ignore[operator]
                    ),
                }
            )
            for source in sources
        ]

    async def _load(self, source_id: UUID) -> JobSource:
        source = await self.repository.get_live(source_id)
        if source is None:
            raise NotFoundError(entity_name="JobSource", entity_id=source_id)
        return source


def _normalized(source_type: SourceType, config: dict) -> dict:
    """Apply the config rule again, as a domain error this time."""
    try:
        return normalize_source_config(source_type, config)
    except ValueError as e:
        raise ValidationError(
            entity_name="JobSource", field="config", message=str(e)
        ) from e


class ListSourcesUseCase(_SourceUseCase):
    """Page through sources."""

    async def execute(
        self,
        params: ListQueryParams,
        *,
        source_type: Optional[SourceType] = None,
        enabled: Optional[bool] = None,
    ) -> Tuple[List[JobSourceAdminSchema], int]:
        """List live sources with their job counts."""
        rows, total = await self.repository.list_paginated(
            params, source_type=source_type, enabled=enabled
        )
        return await self._present(rows), total


class GetSourceUseCase(_SourceUseCase):
    """Read one source."""

    async def execute(self, source_id: UUID) -> JobSourceAdminSchema:
        """Read a live source.

        Raises:
            NotFoundError: No live source has this id
        """
        return (await self._present([await self._load(source_id)]))[0]


class CreateSourceUseCase(_SourceUseCase):
    """Add a source."""

    async def execute(
        self, payload: JobSourceCreateSchema, admin_id: Optional[UUID]
    ) -> JobSourceAdminSchema:
        """Create the source. It is due at once, so the next tick collects it.

        Raises:
            AlreadyExistsError: The slug is taken (deleted sources keep theirs)
        """
        if await self.repository.exists_by_slug(payload.slug):
            raise AlreadyExistsError(
                entity_name="JobSource", field="slug", value=payload.slug
            )
        source = JobSource(
            name=payload.name,
            slug=payload.slug,
            source_type=payload.source_type,
            config=_normalized(payload.source_type, payload.config),
            is_enabled=payload.is_enabled,
            schedule_minutes=payload.schedule_minutes,
            next_run_at=None,
            created_by=admin_id,
            updated_by=admin_id,
        )
        try:
            created = await self.repository.create(source)
        except DuplicateKeyError as e:
            raise AlreadyExistsError(
                entity_name="JobSource", field="slug", value=payload.slug
            ) from e
        return (await self._present([created]))[0]


class UpdateSourceUseCase(_SourceUseCase):
    """Edit a source."""

    async def execute(
        self, source_id: UUID, payload: JobSourceUpdateSchema, admin_id: Optional[UUID]
    ) -> JobSourceAdminSchema:
        """Apply the fields that were sent.

        Re-enabling a paused source makes it due at once rather than waiting
        out an interval that started before it was paused.

        Raises:
            NotFoundError: No live source has this id
            ValidationError: The config breaks the source type's rules
        """
        source = await self._load(source_id)
        changes = payload.model_dump(exclude_unset=True)
        if changes.get("config") is not None:
            changes["config"] = _normalized(source.source_type, changes["config"])
        if changes.get("is_enabled") and not source.is_enabled:
            source.next_run_at = None
        for key, value in changes.items():
            if value is not None:
                setattr(source, key, value)
        source.updated_by = admin_id
        updated = await self.repository.update(source)
        return (await self._present([updated]))[0]


class DeleteSourceUseCase(_SourceUseCase):
    """Remove a source."""

    async def execute(self, source_id: UUID, admin_id: Optional[UUID]) -> None:
        """Soft-delete and disable it. Its jobs stay; they go stale normally.

        Raises:
            NotFoundError: No live source has this id
        """
        source = await self._load(source_id)
        source.is_active = False
        source.is_enabled = False
        source.updated_by = admin_id
        await self.repository.update(source)
