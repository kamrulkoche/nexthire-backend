"""Running a collection.

A run is two steps, split so the slow one can happen after the response:

1. ``StartRunUseCase`` — claim the source (atomically; see
   ``JobSourceRepository.claim``) and record a ``running`` run. Fast; a route
   does this inline so the admin gets the run's id back at once, or a 409.
2. ``ExecuteRunUseCase`` — call the connector, store what it returned, retire
   what the source stopped listing, release the claim, then score the new jobs
   for seekers who want notifications. Slow; runs on the task dispatcher or
   the scheduler's thread, with its own session.

``run_due_collections`` is the scheduler's tick: both steps, for every source
that is due.

This module writes through the job and job_source modules' repositories and
calls the recommendation and notification modules' use cases. It is the one
place that orchestrates across modules, and does so explicitly rather than
through an event bus — there is one producer and two consumers, and the call
order matters (matching must see the stored jobs).
"""

from datetime import timedelta
from typing import Callable, Dict, List, Optional
from uuid import UUID

from src.shared.infrastructure.database import MongoSession

from src.modules.job.domain.entities.job import Job
from src.modules.job.domain.services.fingerprint import job_fingerprint
from src.modules.job.infrastructure.repositories.job_repository import JobRepository
from src.modules.job_source.domain.entities.job_source import JobSource
from src.modules.job_source.infrastructure.repositories.job_source_repository import (
    JobSourceRepository,
)
from src.modules.notification.application.use_cases.notification_use_cases import (
    NotifyUseCase,
)
from src.modules.notification.domain.enums.notification_kind import NotificationKind
from src.modules.recommendation.application.use_cases.recommendation_use_cases import (
    MatchNewJobsUseCase,
)
from src.modules.recommendation.domain.services.job_scorer import JobScorer
from src.modules.recommendation.infrastructure.scorers.factory import build_scorer
from src.shared.domain.exceptions.external_service_error import ExternalServiceError
from src.shared.domain.exceptions.not_found_error import NotFoundError
from src.shared.domain.text import clip
from src.shared.domain.time import utc_now
from src.shared.infrastructure.database import get_db_context
from src.shared.infrastructure.logging import get_logger
from src.shared.utils.config import settings

from ...domain.entities.collection_run import CollectionRun
from ...domain.enums.run_status import RunStatus
from ...domain.enums.run_trigger import RunTrigger
from ...domain.exceptions import RunInProgressError
from ...domain.services.job_connector import ConnectorResult, JobConnector
from ...domain.value_objects.collected_job import CollectedJob
from ...infrastructure.external.connectors.registry import connector_for
from ...infrastructure.repositories.collection_run_repository import (
    CollectionRunRepository,
)

logger = get_logger(__name__)

#: Jobs written per commit.
BATCH_SIZE = 200

ConnectorFactory = Callable[[JobSource], JobConnector]


def default_connector_factory(source: JobSource) -> JobConnector:
    """The registered connector for the source's type."""
    return connector_for(source.source_type)


class StartRunUseCase:
    """Claim a source and record a running run."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.sources = JobSourceRepository(session)
        self.runs = CollectionRunRepository(session)

    async def execute(
        self,
        source_id: UUID,
        *,
        trigger: RunTrigger,
        triggered_by: Optional[UUID] = None,
    ) -> CollectionRun:
        """Start a run of one source.

        Raises:
            NotFoundError: No live source has this id
            RunInProgressError: Another run holds the source's claim
        """
        source = await self.sources.get_live(source_id)
        if source is None:
            raise NotFoundError(entity_name="JobSource", entity_id=source_id)
        now = utc_now()
        until = now + timedelta(minutes=settings.collection_lock_minutes)
        if not await self.sources.claim(source_id, now, until):
            raise RunInProgressError(source_id)
        return await self.runs.create(
            CollectionRun(
                source_id=source_id,
                trigger=trigger,
                status=RunStatus.RUNNING,
                triggered_by=triggered_by,
                started_at=now,
            )
        )


class ExecuteRunUseCase:
    """Do the work of a started run."""

    def __init__(
        self,
        session: MongoSession,
        *,
        scorer: Optional[JobScorer] = None,
        connector_factory: ConnectorFactory = default_connector_factory,
    ) -> None:
        """Inject the session, the scorer for new-job matching, and connectors.

        Args:
            session: A session of the run's own — never a request's
            scorer: Scores new jobs for seekers; defaults to ``build_scorer()``
            connector_factory: Source → connector; tests pass a fake
        """
        self.session = session
        self.scorer = scorer
        self.connector_factory = connector_factory
        self.sources = JobSourceRepository(session)
        self.runs = CollectionRunRepository(session)
        self.jobs = JobRepository(session)

    async def execute(self, run_id: UUID) -> CollectionRun:
        """Run the connector and store the result. Never raises for a source
        failure: the run is recorded as failed and the claim released."""
        run = await self.runs.get_by_id(run_id)
        if run is None:
            raise NotFoundError(entity_name="CollectionRun", entity_id=run_id)
        source = await self.sources.get_by_id(run.source_id)
        if source is None:
            raise NotFoundError(entity_name="JobSource", entity_id=run.source_id)

        try:
            result = await self.connector_factory(source).fetch(
                dict(source.config), settings.collection_max_jobs_per_run
            )
        except ExternalServiceError as e:
            return await self._fail(run, source, e.message)
        except Exception as e:
            logger.error(f"Connector crashed for {source.slug}: {e}", exc_info=True)
            return await self._fail(run, source, "The connector failed unexpectedly.")

        try:
            new_ids = await self._store(run, source, result)
        except Exception as e:
            logger.error(f"Storing jobs failed for {source.slug}: {e}", exc_info=True)
            self.session.rollback()
            return await self._fail(run, source, "Storing the jobs failed.")

        finished = utc_now()
        run.status = RunStatus.PARTIAL if result.skipped else RunStatus.SUCCEEDED
        run.finished_at = finished
        self.session.add(run)
        self.session.commit()
        await self.sources.release(
            source.id,  # type: ignore[arg-type]
            status=run.status,
            finished_at=finished,
            next_run_at=finished + timedelta(minutes=source.schedule_minutes),
        )
        logger.info(
            f"Run {run.id} of {source.slug}: fetched={run.fetched_count} "
            f"created={run.created_count} updated={run.updated_count} "
            f"duplicates={run.duplicate_count} skipped={run.skipped_count} "
            f"deactivated={run.deactivated_count}"
        )

        if new_ids:
            try:
                scorer = self.scorer or build_scorer()
                await MatchNewJobsUseCase(self.session, scorer).execute(new_ids)
            except Exception as e:
                # Matching is a bonus; the run itself succeeded.
                logger.error(f"Post-run matching failed: {e}", exc_info=True)
                self.session.rollback()
        return run

    async def _store(
        self, run: CollectionRun, source: JobSource, result: ConnectorResult
    ) -> List[UUID]:
        """Insert new jobs, refresh known ones, retire stale ones.

        Returns:
            Ids of the jobs created that are NOT duplicates — the ones worth
            matching against seekers.
        """
        assert source.id is not None
        now = utc_now()

        # One posting per external id, first wins: some feeds repeat items.
        unique: Dict[str, CollectedJob] = {}
        for collected in result.jobs:
            unique.setdefault(collected.external_id, collected)

        existing = await self.jobs.by_external_ids(source.id, unique)
        fingerprints = {
            ext_id: job_fingerprint(c.title, c.company, c.location)
            for ext_id, c in unique.items()
        }
        originals = await self.jobs.originals_by_fingerprint(
            (fp for ext_id, fp in fingerprints.items() if ext_id not in existing),
            source.id,
        )

        pending: List[Job] = []
        new_ids: List[UUID] = []
        first_in_batch: Dict[str, UUID] = {}
        created = updated = duplicates = 0

        for ext_id, collected in unique.items():
            fingerprint = fingerprints[ext_id]
            job = existing.get(ext_id)
            if job is not None:
                _apply(job, collected)
                job.fingerprint = fingerprint
                job.last_seen_at = now
                job.is_active = True
                job.updated_at = now
                updated += 1
            else:
                job = Job(
                    source_id=source.id,
                    external_id=ext_id,
                    first_seen_at=now,
                    last_seen_at=now,
                    fingerprint=fingerprint,
                    title=collected.title,
                    company=collected.company,
                    url=collected.url,
                )
                _apply(job, collected)
                original = originals.get(fingerprint) or first_in_batch.get(fingerprint)
                if original is not None:
                    job.duplicate_of_id = original
                    duplicates += 1
                else:
                    assert job.id is not None
                    first_in_batch[fingerprint] = job.id
                    new_ids.append(job.id)
                created += 1
            pending.append(job)
            if len(pending) >= BATCH_SIZE:
                await self.jobs.save_batch(pending)
                pending = []
        if pending:
            await self.jobs.save_batch(pending)

        deactivated = await self.jobs.deactivate_stale(
            source.id, now - timedelta(days=settings.job_stale_after_days)
        )

        run.fetched_count = len(result.jobs)
        run.created_count = created
        run.updated_count = updated
        run.duplicate_count = duplicates
        run.skipped_count = result.skipped
        run.deactivated_count = deactivated
        return new_ids

    async def _fail(
        self, run: CollectionRun, source: JobSource, message: str
    ) -> CollectionRun:
        """Record the failure, release the claim, tell the admins."""
        finished = utc_now()
        run.status = RunStatus.FAILED
        run.finished_at = finished
        run.error_message = clip(message, 500)
        self.session.add(run)
        self.session.commit()
        # Back off a full interval rather than retrying on the next tick: a
        # source that is down is usually down for a while, and hammering it
        # helps nobody.
        await self.sources.release(
            source.id,  # type: ignore[arg-type]
            status=RunStatus.FAILED,
            finished_at=finished,
            next_run_at=finished + timedelta(minutes=source.schedule_minutes),
        )
        logger.warning(f"Run {run.id} of {source.slug} failed: {message}")
        try:
            await NotifyUseCase(self.session).to_admins(
                kind=NotificationKind.RUN_FAILED,
                title=f"Collection failed: {source.name}",
                body=message,
                link="/admin/runs",
            )
        except Exception as e:
            logger.error(f"Could not notify admins of a failed run: {e}")
            self.session.rollback()
        return run


def _apply(job: Job, collected: CollectedJob) -> None:
    """Copy a posting's fields onto a job row. Moderation flags are untouched."""
    job.title = collected.title
    job.company = collected.company
    job.url = collected.url
    job.description = collected.description
    job.location = collected.location
    job.is_remote = collected.is_remote
    job.employment_type = collected.employment_type
    job.salary_min = collected.salary_min
    job.salary_max = collected.salary_max
    job.salary_currency = collected.salary_currency
    job.category = collected.category
    job.tags = list(collected.tags)
    job.posted_at = collected.posted_at


async def run_due_collections() -> int:
    """The scheduler's tick: run every due source, one after another.

    Opens its own session. A source another process claimed first is skipped
    quietly — that is the claim working, not an error.

    Returns:
        How many runs this tick executed
    """
    executed = 0
    with get_db_context() as session:
        due = await JobSourceRepository(session).due_source_ids(utc_now())
        if not due:
            return 0
        scorer = build_scorer()
        for source_id in due:
            try:
                run = await StartRunUseCase(session).execute(
                    source_id, trigger=RunTrigger.SCHEDULED
                )
            except (RunInProgressError, NotFoundError):
                continue
            assert run.id is not None
            await ExecuteRunUseCase(session, scorer=scorer).execute(run.id)
            executed += 1
    return executed
