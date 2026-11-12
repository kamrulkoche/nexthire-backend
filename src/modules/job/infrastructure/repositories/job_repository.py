"""
Job repository — search for seekers, moderation for admins, and the primitives
the collector writes through.

THE visibility rule lives here and nowhere else (``visible_filter``): a
seeker sees a job when it is active, not hidden and not a duplicate. Every
seeker-facing read goes through it, the way every public read in hgs-backend
goes through its repository's published-and-active gate.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Type
from uuid import UUID

from pymongo import ASCENDING, DESCENDING

from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.repository_error import RepositoryError
from src.shared.domain.time import utc_now
from src.shared.infrastructure.base_repository import BaseRepository
from src.shared.infrastructure.database import MongoSession
from src.shared.infrastructure.ordering import contains_ci, resolve_sort_column

from ...domain.entities.job import Job
from ...domain.enums.employment_type import EmploymentType

#: Fields a job list may be sorted by — see `resolve_sort_column`. `posted_at`
#: sorts by the posting date, falling back to when we first saw the job (the
#: stored, derived ``effective_posted_at``).
SORTABLE = {"posted_at", "salary_max", "title", "company", "last_seen_at"}

DEFAULT_SORT = "posted_at"

#: Search terms beyond this many are ignored — each adds an OR over three fields.
MAX_SEARCH_TERMS = 6

#: The stored ``coalesce(posted_at, first_seen_at)`` — see ``Job.effective_posted_at``.
EFFECTIVE_POSTED = "effective_posted_at"


@dataclass(frozen=True)
class JobSearchFilters:
    """The filters on the Job Search screen. Every field is optional."""

    location: Optional[str] = None
    remote: Optional[bool] = None
    employment_type: Optional[EmploymentType] = None
    posted_within_days: Optional[int] = None
    salary_min: Optional[int] = None
    source_id: Optional[UUID] = None


def visible_filter() -> dict[str, Any]:
    """The one rule for what a seeker may see, as a MongoDB filter on ``jobs``.

    Active AND not hidden AND not a duplicate. ``duplicate_of_id: None``
    matches a missing field as well as an explicit null.
    """
    return {"is_active": True, "is_hidden": False, "duplicate_of_id": None}


def _and(conditions: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine filter clauses; ``$and`` keeps two ``$or`` clauses apart."""
    if not conditions:
        return {}
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


class JobRepository(BaseRepository[Job]):
    """Repository for Job database operations."""

    def __init__(self, session: MongoSession, model: Type[Job] = Job):
        """Initialize the job repository."""
        super().__init__(session, model)

    async def create(self, entity: Job) -> Job:
        """Persist a new job, with its derived sort date."""
        entity.sync_effective_posted()
        return await super().create(entity)

    async def update(self, entity: Job) -> Job:
        """Persist changes, keeping the derived sort date in step."""
        entity.sync_effective_posted()
        return await super().update(entity)

    # ------------------------------------------------------------------
    # Seeker reads
    # ------------------------------------------------------------------

    def _filter_conditions(
        self, search: Optional[str], filters: JobSearchFilters
    ) -> list[dict[str, Any]]:
        conditions: list[dict[str, Any]] = []
        if search:
            for term in search.split()[:MAX_SEARCH_TERMS]:
                pattern = contains_ci(term)
                conditions.append(
                    {
                        "$or": [
                            {"title": pattern},
                            {"company": pattern},
                            {"description": pattern},
                        ]
                    }
                )
        if filters.location:
            conditions.append({"location": contains_ci(filters.location.strip())})
        if filters.remote is not None:
            conditions.append({"is_remote": filters.remote})
        if filters.employment_type is not None:
            conditions.append({"employment_type": filters.employment_type.value})
        if filters.posted_within_days:
            since = utc_now() - timedelta(days=filters.posted_within_days)
            conditions.append({EFFECTIVE_POSTED: {"$gte": since}})
        if filters.salary_min:
            conditions.append(
                {
                    "$or": [
                        {"salary_max": {"$gte": filters.salary_min}},
                        {
                            "salary_max": None,
                            "salary_min": {"$gte": filters.salary_min},
                        },
                    ]
                }
            )
        if filters.source_id is not None:
            conditions.append({"source_id": filters.source_id})
        return conditions

    def _page(self, query: dict[str, Any], params: ListQueryParams) -> List[Job]:
        """One page of ``query`` in the order ``params`` asks for."""
        if params.sort in (None, "posted_at"):
            field = EFFECTIVE_POSTED
            # Newest first unless the caller asked for ascending explicitly.
            descending = params.sort is None or params.order == "desc"
        else:
            field = resolve_sort_column(params.sort, SORTABLE, DEFAULT_SORT)
            if field == "posted_at":
                field = EFFECTIVE_POSTED
            descending = params.order == "desc"
        direction = DESCENDING if descending else ASCENDING

        if field == "salary_max":
            # Unstated salaries last in either direction. MongoDB sorts null
            # lowest, so stated and unstated salaries are read as two ranges.
            stated = _and([query, {"salary_max": {"$ne": None}}])
            unstated = _and([query, {"salary_max": None}])
            n_stated = self.collection.count_documents(stated)
            rows: List[Job] = []
            if params.offset < n_stated:
                rows = self.load_many(
                    self.collection.find(stated)
                    .sort([("salary_max", direction), ("_id", ASCENDING)])
                    .skip(params.offset)
                    .limit(params.limit)
                )
            remaining = params.limit - len(rows)
            if remaining > 0:
                skip = max(0, params.offset - n_stated)
                rows += self.load_many(
                    self.collection.find(unstated)
                    .sort([("_id", ASCENDING)])
                    .skip(skip)
                    .limit(remaining)
                )
            return rows

        cursor = (
            self.collection.find(query)
            .sort([(field, direction), ("_id", ASCENDING)])
            .skip(params.offset)
            .limit(params.limit)
        )
        return self.load_many(cursor)

    async def search(
        self, params: ListQueryParams, filters: JobSearchFilters
    ) -> Tuple[List[Job], int]:
        """Search the jobs a seeker may see.

        Args:
            params: Page, size, free-text search (every word must match title,
                company or description) and sort
            filters: The screen's filters

        Returns:
            ``(rows_for_this_page, total_matching_rows)``
        """
        try:
            query = _and(
                [visible_filter()]
                + self._filter_conditions(params.normalized_search, filters)
            )
            total = self.collection.count_documents(query)
            return self._page(query, params), int(total)
        except Exception as e:
            raise RepositoryError(
                entity_name="Job", operation="search", message=str(e)
            ) from e

    async def get_visible(self, job_id: UUID) -> Optional[Job]:
        """One job a seeker may see, or None."""
        try:
            return self.load(
                self.collection.find_one({"_id": job_id, **visible_filter()})
            )
        except Exception as e:
            raise RepositoryError(
                entity_name="Job", operation="get_visible", message=str(e)
            ) from e

    async def get_many(self, job_ids: Iterable[UUID]) -> Dict[UUID, Job]:
        """Load jobs by id, visible or not — for lists that already own a link
        to the job (saved jobs, matches) and must still render a removed one."""
        ids = list(set(job_ids))
        if not ids:
            return {}
        try:
            rows = self.load_many(self.collection.find({"_id": {"$in": ids}}))
            return {row.id: row for row in rows}
        except Exception as e:
            raise RepositoryError(
                entity_name="Job", operation="get_many", message=str(e)
            ) from e

    async def visible_ids(self, job_ids: Iterable[UUID]) -> List[UUID]:
        """Which of these jobs a seeker may still see — the replacement for a
        SQL join against ``jobs`` with the visibility rule."""
        ids = list(set(job_ids))
        if not ids:
            return []
        try:
            cursor = self.collection.find(
                {"_id": {"$in": ids}, **visible_filter()}, {"_id": 1}
            )
            return [document["_id"] for document in cursor]
        except Exception as e:
            raise RepositoryError(
                entity_name="Job", operation="visible_ids", message=str(e)
            ) from e

    async def visible_candidates(
        self,
        *,
        since: datetime,
        exclude_ids: Sequence[UUID],
        remote_only: bool,
        employment_types: Sequence[EmploymentType],
        only_ids: Optional[Sequence[UUID]] = None,
        limit: int = 300,
    ) -> List[Job]:
        """Recent visible jobs, for the recommendation pre-filter.

        The cheap, structural filters run here in the database; keyword
        relevance is scored in Python over what comes back, because it needs
        the seeker's whole keyword list against title, tags and description.

        Args:
            since: Ignore jobs posted (or first seen) before this
            exclude_ids: Jobs already scored for this seeker
            remote_only: Only remote jobs
            employment_types: Allowed types; empty means any
            only_ids: Restrict to these jobs (a run's new arrivals)
            limit: Most rows to return, newest first

        Returns:
            Candidate jobs
        """
        try:
            conditions: list[dict[str, Any]] = [
                visible_filter(),
                {EFFECTIVE_POSTED: {"$gte": since}},
            ]
            if exclude_ids:
                conditions.append({"_id": {"$nin": list(exclude_ids)}})
            if remote_only:
                conditions.append({"is_remote": True})
            if employment_types:
                conditions.append(
                    {
                        "$or": [
                            {
                                "employment_type": {
                                    "$in": [t.value for t in employment_types]
                                }
                            },
                            {"employment_type": None},
                        ]
                    }
                )
            if only_ids is not None:
                if not only_ids:
                    return []
                conditions.append({"_id": {"$in": list(only_ids)}})
            cursor = (
                self.collection.find(_and(conditions))
                .sort([(EFFECTIVE_POSTED, DESCENDING), ("_id", ASCENDING)])
                .limit(limit)
            )
            return self.load_many(cursor)
        except Exception as e:
            raise RepositoryError(
                entity_name="Job", operation="visible_candidates", message=str(e)
            ) from e

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------

    async def admin_list(
        self,
        params: ListQueryParams,
        filters: JobSearchFilters,
        *,
        hidden: Optional[bool] = None,
        active: Optional[bool] = None,
    ) -> Tuple[List[Job], int]:
        """Every job, hidden, stale and duplicate ones included, for moderation."""
        try:
            conditions = self._filter_conditions(params.normalized_search, filters)
            if hidden is not None:
                conditions.append({"is_hidden": hidden})
            if active is not None:
                conditions.append({"is_active": active})
            query = _and(conditions)
            total = self.collection.count_documents(query)
            return self._page(query, params), int(total)
        except Exception as e:
            raise RepositoryError(
                entity_name="Job", operation="admin_list", message=str(e)
            ) from e

    # ------------------------------------------------------------------
    # Collector primitives
    # ------------------------------------------------------------------

    async def by_external_ids(
        self, source_id: UUID, external_ids: Iterable[str]
    ) -> Dict[str, Job]:
        """The jobs a source already has, keyed by the source's own id."""
        ids = list(set(external_ids))
        if not ids:
            return {}
        try:
            rows = self.load_many(
                self.collection.find(
                    {"source_id": source_id, "external_id": {"$in": ids}}
                )
            )
            return {row.external_id: row for row in rows}
        except Exception as e:
            raise RepositoryError(
                entity_name="Job", operation="by_external_ids", message=str(e)
            ) from e

    async def originals_by_fingerprint(
        self, fingerprints: Iterable[str], exclude_source_id: UUID
    ) -> Dict[str, UUID]:
        """For each fingerprint, the visible job from ANOTHER source that holds
        it — the copy a new arrival should be marked a duplicate of."""
        prints = list(set(fingerprints))
        if not prints:
            return {}
        try:
            cursor = self.collection.find(
                {
                    **visible_filter(),
                    "fingerprint": {"$in": prints},
                    "source_id": {"$ne": exclude_source_id},
                },
                {"fingerprint": 1},
            ).sort([("first_seen_at", ASCENDING), ("_id", ASCENDING)])
            originals: Dict[str, UUID] = {}
            for document in cursor:
                originals.setdefault(document["fingerprint"], document["_id"])
            return originals
        except Exception as e:
            raise RepositoryError(
                entity_name="Job", operation="originals_by_fingerprint", message=str(e)
            ) from e

    async def save_batch(self, jobs: Sequence[Job]) -> None:
        """Insert or update a batch of jobs in one commit."""
        try:
            for job in jobs:
                job.sync_effective_posted()
            self.session.add_all(list(jobs))
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            raise RepositoryError(
                entity_name="Job", operation="save_batch", message=str(e)
            ) from e

    async def deactivate_stale(self, source_id: UUID, seen_before: datetime) -> int:
        """Mark a source's jobs inactive when it has stopped listing them.

        Returns:
            How many jobs were deactivated
        """
        try:
            result = self.collection.update_many(
                {
                    "source_id": source_id,
                    "is_active": True,
                    "last_seen_at": {"$lt": seen_before},
                },
                {"$set": {"is_active": False, "updated_at": utc_now()}},
            )
            return int(result.modified_count)
        except Exception as e:
            raise RepositoryError(
                entity_name="Job", operation="deactivate_stale", message=str(e)
            ) from e

    # ------------------------------------------------------------------
    # Counts
    # ------------------------------------------------------------------

    async def active_counts_by_source(
        self, source_ids: Iterable[UUID]
    ) -> Dict[UUID, int]:
        """Live, unhidden jobs per source, for the Sources screen."""
        ids = list(set(source_ids))
        if not ids:
            return {}
        try:
            rows = self.collection.aggregate(
                [
                    {
                        "$match": {
                            "source_id": {"$in": ids},
                            "is_active": True,
                            "is_hidden": False,
                        }
                    },
                    {"$group": {"_id": "$source_id", "n": {"$sum": 1}}},
                ]
            )
            return {row["_id"]: int(row["n"]) for row in rows}
        except Exception as e:
            raise RepositoryError(
                entity_name="Job", operation="active_counts_by_source", message=str(e)
            ) from e

    async def visible_count(self, since: Optional[datetime] = None) -> int:
        """Jobs a seeker can see; with ``since``, only those first seen after it."""
        try:
            query = visible_filter()
            if since is not None:
                query["first_seen_at"] = {"$gte": since}
            return int(self.collection.count_documents(query))
        except Exception as e:
            raise RepositoryError(
                entity_name="Job", operation="visible_count", message=str(e)
            ) from e

    async def moderation_counts(self) -> Dict[str, int]:
        """Totals for the admin dashboard."""
        try:
            count = self.collection.count_documents
            return {
                "total": int(count({})),
                "visible": await self.visible_count(),
                "hidden": int(count({"is_hidden": True})),
                "stale": int(count({"is_active": False})),
                "duplicates": int(count({"duplicate_of_id": {"$ne": None}})),
            }
        except RepositoryError:
            raise
        except Exception as e:
            raise RepositoryError(
                entity_name="Job", operation="moderation_counts", message=str(e)
            ) from e

    async def visible_company_count(self) -> int:
        """Distinct companies with a visible job — for the landing page."""
        try:
            return len(self.collection.distinct("company", visible_filter()))
        except Exception as e:
            raise RepositoryError(
                entity_name="Job", operation="visible_company_count", message=str(e)
            ) from e
