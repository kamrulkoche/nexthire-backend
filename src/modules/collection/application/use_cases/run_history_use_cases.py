"""Use cases behind the run-history screen."""

from typing import List, Optional, Sequence, Tuple
from uuid import UUID

from src.shared.infrastructure.database import MongoSession

from src.modules.job_source.infrastructure.repositories.job_source_repository import (
    JobSourceRepository,
)
from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.not_found_error import NotFoundError
from src.shared.domain.time import as_utc

from ...domain.entities.collection_run import CollectionRun
from ...domain.enums.run_status import RunStatus
from ...domain.enums.run_trigger import RunTrigger
from ...infrastructure.repositories.collection_run_repository import (
    CollectionRunRepository,
)
from ..schemas.collection_run_schema import CollectionRunSchema


def present_runs(
    session: MongoSession, runs: Sequence[CollectionRun]
) -> List[CollectionRunSchema]:
    """Runs with their source's name and type, and a duration once finished."""
    sources = JobSourceRepository(session).names_for(run.source_id for run in runs)
    items = []
    for run in runs:
        name, source_type = sources.get(run.source_id, (None, None))
        started, finished = as_utc(run.started_at), as_utc(run.finished_at)
        duration = (
            int((finished - started).total_seconds() * 1000)
            if finished and started
            else None
        )
        items.append(
            CollectionRunSchema.model_validate(run).model_copy(
                update={
                    "source_name": name,
                    "source_type": source_type,
                    "duration_ms": duration,
                }
            )
        )
    return items


class ListRunsUseCase:
    """Page through run history."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.session = session
        self.runs = CollectionRunRepository(session)

    async def execute(
        self,
        params: ListQueryParams,
        *,
        source_id: Optional[UUID] = None,
        status: Optional[RunStatus] = None,
        trigger: Optional[RunTrigger] = None,
    ) -> Tuple[List[CollectionRunSchema], int]:
        """List runs, newest first by default."""
        rows, total = await self.runs.list_paginated(
            params, source_id=source_id, status=status, trigger=trigger
        )
        return present_runs(self.session, rows), total


class GetRunUseCase:
    """Read one run."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.session = session
        self.runs = CollectionRunRepository(session)

    async def execute(self, run_id: UUID) -> CollectionRunSchema:
        """Read a run by id.

        Raises:
            NotFoundError: No run has this id
        """
        run = await self.runs.get_by_id(run_id)
        if run is None:
            raise NotFoundError(entity_name="CollectionRun", entity_id=run_id)
        return present_runs(self.session, [run])[0]
