"""Collection run repository — the run-history screen and the dashboards."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Type
from uuid import UUID

from pymongo import ASCENDING, DESCENDING

from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.repository_error import RepositoryError
from src.shared.infrastructure.base_repository import BaseRepository
from src.shared.infrastructure.database import MongoSession
from src.shared.infrastructure.ordering import resolve_sort_column

from ...domain.entities.collection_run import CollectionRun
from ...domain.enums.run_status import RunStatus
from ...domain.enums.run_trigger import RunTrigger

#: Fields the run history may be sorted by — see `resolve_sort_column`.
SORTABLE = {"started_at", "finished_at", "status", "created_count", "fetched_count"}

DEFAULT_SORT = "started_at"


class CollectionRunRepository(BaseRepository[CollectionRun]):
    """Repository for CollectionRun database operations."""

    def __init__(
        self, session: MongoSession, model: Type[CollectionRun] = CollectionRun
    ):
        """Initialize the collection run repository."""
        super().__init__(session, model)

    async def list_paginated(
        self,
        params: ListQueryParams,
        *,
        source_id: Optional[UUID] = None,
        status: Optional[RunStatus] = None,
        trigger: Optional[RunTrigger] = None,
    ) -> Tuple[List[CollectionRun], int]:
        """Run history, newest first by default."""
        try:
            query: dict[str, Any] = {}
            if source_id is not None:
                query["source_id"] = source_id
            if status is not None:
                query["status"] = status.value
            if trigger is not None:
                query["trigger"] = trigger.value
            total = self.collection.count_documents(query)
            field = resolve_sort_column(params.sort, SORTABLE, DEFAULT_SORT)
            descending = params.order == "desc" or params.sort is None
            cursor = (
                self.collection.find(query)
                .sort(
                    [
                        (field, DESCENDING if descending else ASCENDING),
                        ("_id", ASCENDING),
                    ]
                )
                .skip(params.offset)
                .limit(params.limit)
            )
            return self.load_many(cursor), int(total)
        except Exception as e:
            raise RepositoryError(
                entity_name="CollectionRun", operation="list_paginated", message=str(e)
            ) from e

    async def counts_since(self, since: datetime) -> Dict[str, int]:
        """``{status: count}`` for runs started since ``since``."""
        try:
            rows = self.collection.aggregate(
                [
                    {"$match": {"started_at": {"$gte": since}}},
                    {"$group": {"_id": "$status", "n": {"$sum": 1}}},
                ]
            )
            return {str(row["_id"]): int(row["n"]) for row in rows}
        except Exception as e:
            raise RepositoryError(
                entity_name="CollectionRun", operation="counts_since", message=str(e)
            ) from e

    async def recent(self, limit: int) -> List[CollectionRun]:
        """The latest runs, for the admin dashboard."""
        try:
            cursor = (
                self.collection.find({})
                .sort([("started_at", DESCENDING), ("_id", ASCENDING)])
                .limit(limit)
            )
            return self.load_many(cursor)
        except Exception as e:
            raise RepositoryError(
                entity_name="CollectionRun", operation="recent", message=str(e)
            ) from e
