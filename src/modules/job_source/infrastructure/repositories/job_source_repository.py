"""
Job source repository — the Sources screen's queries and the run claim.
"""

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple, Type
from uuid import UUID

from pymongo import ASCENDING

from src.modules.collection.domain.enums.run_status import RunStatus
from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.repository_error import RepositoryError
from src.shared.infrastructure.base_repository import BaseRepository
from src.shared.infrastructure.database import MongoSession
from src.shared.infrastructure.ordering import (
    contains_ci,
    resolve_sort_column,
    sort_spec,
)

from ...domain.entities.job_source import JobSource
from ...domain.enums.source_type import SourceType

#: Fields the Sources screen may sort by — see `resolve_sort_column`.
SORTABLE = {"name", "source_type", "last_run_at", "next_run_at", "created_at"}

DEFAULT_SORT = "name"


def _unclaimed(now: datetime) -> dict[str, Any]:
    """No claim, or one that has lapsed. ``None`` also matches a missing field."""
    return {"$or": [{"locked_until": None}, {"locked_until": {"$lt": now}}]}


class JobSourceRepository(BaseRepository[JobSource]):
    """Repository for JobSource database operations."""

    def __init__(self, session: MongoSession, model: Type[JobSource] = JobSource):
        """Initialize the job source repository."""
        super().__init__(session, model)

    async def get_live(self, source_id: UUID) -> Optional[JobSource]:
        """A source that has not been deleted, or None."""
        source = await self.get_by_id(source_id)
        if source is None or not source.is_active:
            return None
        return source

    def names_for(
        self, source_ids: Iterable[UUID]
    ) -> Dict[UUID, Tuple[str, SourceType]]:
        """``{id: (name, type)}`` for these sources, deleted ones included —
        a job or a run still names the source it came from."""
        ids = list(set(source_ids))
        if not ids:
            return {}
        try:
            cursor = self.collection.find(
                {"_id": {"$in": ids}}, {"name": 1, "source_type": 1}
            )
            return {d["_id"]: (d["name"], SourceType(d["source_type"])) for d in cursor}
        except Exception as e:
            raise RepositoryError(
                entity_name="JobSource", operation="names_for", message=str(e)
            ) from e

    async def exists_by_slug(self, slug: str) -> bool:
        """Whether any source — deleted ones included — holds this slug.

        Deleted sources keep their slug, as every soft-deleted row does in
        hgs-backend: the unique index still covers it.
        """
        try:
            return self.collection.count_documents({"slug": slug}, limit=1) > 0
        except Exception as e:
            raise RepositoryError(
                entity_name="JobSource", operation="exists_by_slug", message=str(e)
            ) from e

    async def list_paginated(
        self,
        params: ListQueryParams,
        *,
        source_type: Optional[SourceType] = None,
        enabled: Optional[bool] = None,
    ) -> Tuple[List[JobSource], int]:
        """List live sources for the Sources screen.

        Returns:
            ``(rows_for_this_page, total_matching_rows)``
        """
        try:
            query: dict[str, Any] = {"is_active": True}
            if source_type is not None:
                query["source_type"] = source_type.value
            if enabled is not None:
                query["is_enabled"] = enabled
            term = params.normalized_search
            if term:
                query["$or"] = [
                    {"name": contains_ci(term)},
                    {"slug": contains_ci(term)},
                ]

            total = self.collection.count_documents(query)
            field = resolve_sort_column(params.sort, SORTABLE, DEFAULT_SORT)
            cursor = (
                self.collection.find(query)
                .sort(sort_spec(field, params.order, "created_at"))
                .skip(params.offset)
                .limit(params.limit)
            )
            return self.load_many(cursor), int(total)
        except Exception as e:
            raise RepositoryError(
                entity_name="JobSource", operation="list_paginated", message=str(e)
            ) from e

    async def due_source_ids(self, now: datetime) -> List[UUID]:
        """Sources the scheduler should run now.

        Live, enabled, due (``next_run_at`` null or past) and unclaimed. The
        claim is re-checked atomically by ``claim``; this is only the shortlist.
        """
        try:
            cursor = self.collection.find(
                {
                    "is_active": True,
                    "is_enabled": True,
                    "$and": [
                        {
                            "$or": [
                                {"next_run_at": None},
                                {"next_run_at": {"$lte": now}},
                            ]
                        },
                        _unclaimed(now),
                    ],
                },
                {"_id": 1},
            ).sort([("next_run_at", ASCENDING), ("_id", ASCENDING)])
            return [d["_id"] for d in cursor]
        except Exception as e:
            raise RepositoryError(
                entity_name="JobSource", operation="due_source_ids", message=str(e)
            ) from e

    async def claim(self, source_id: UUID, now: datetime, until: datetime) -> bool:
        """Take the run claim on a source, atomically.

        One ``update_one`` whose filter only matches an unclaimed (or expired)
        claim. MongoDB applies a single-document update atomically, so
        whichever process's update lands first matches the document; every
        other matches nothing and backs off. This holds across processes and
        machines, which an in-memory lock would not.

        Returns:
            True if this caller now holds the claim
        """
        try:
            result = self.collection.update_one(
                {"_id": source_id, "is_active": True, **_unclaimed(now)},
                {"$set": {"locked_until": until}},
            )
            return result.matched_count > 0
        except Exception as e:
            raise RepositoryError(
                entity_name="JobSource", operation="claim", message=str(e)
            ) from e

    async def release(
        self,
        source_id: UUID,
        *,
        status: RunStatus,
        finished_at: datetime,
        next_run_at: datetime,
    ) -> None:
        """Record a finished run on the source and drop the claim.

        A direct update rather than ``BaseRepository.update``: a run is not an
        edit of the source, so ``updated_at`` must not move.
        """
        try:
            self.collection.update_one(
                {"_id": source_id},
                {
                    "$set": {
                        "locked_until": None,
                        "last_run_at": finished_at,
                        "last_run_status": status.value,
                        "next_run_at": next_run_at,
                    }
                },
            )
        except Exception as e:
            raise RepositoryError(
                entity_name="JobSource", operation="release", message=str(e)
            ) from e

    async def counts(self) -> Tuple[int, int]:
        """``(live_sources, enabled_sources)`` for the admin dashboard."""
        try:
            total = self.collection.count_documents({"is_active": True})
            enabled = self.collection.count_documents(
                {"is_active": True, "is_enabled": True}
            )
            return int(total), int(enabled)
        except Exception as e:
            raise RepositoryError(
                entity_name="JobSource", operation="counts", message=str(e)
            ) from e
