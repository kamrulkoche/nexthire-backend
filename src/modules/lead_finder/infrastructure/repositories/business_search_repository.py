"""
Business search repository.

Every read a user can reach takes their ``user_id`` and filters on it. The
worker's reads (``get_by_id``, ``claim``) take only the search id, because the
worker runs on behalf of the search's owner and was handed the id by them.
"""

from datetime import datetime
from typing import Any, List, Optional, Tuple, Type
from uuid import UUID

from pymongo import ASCENDING, DESCENDING

from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.repository_error import RepositoryError
from src.shared.infrastructure.base_repository import BaseRepository
from src.shared.infrastructure.database import MongoSession
from src.shared.infrastructure.ordering import contains_ci, resolve_sort_column

from ...domain.entities.business_search import BusinessSearch
from ...domain.entities.lead_export import LeadExport
from ...domain.entities.saved_lead import SavedLead
from ...domain.entities.search_result import BusinessSearchResult
from ...domain.enums import SearchStatus

SORTABLE = {"created_at", "keyword", "total_results", "leads_found", "status"}

_ACTIVE = [SearchStatus.QUEUED.value, SearchStatus.RUNNING.value]


class BusinessSearchRepository(BaseRepository[BusinessSearch]):
    """Repository for BusinessSearch database operations."""

    def __init__(
        self, session: MongoSession, model: Type[BusinessSearch] = BusinessSearch
    ):
        """Initialize the business search repository."""
        super().__init__(session, model)

    async def get_for_user(
        self, user_id: UUID, search_id: UUID
    ) -> Optional[BusinessSearch]:
        """The caller's search, or None (including someone else's)."""
        try:
            return self.load(
                self.collection.find_one({"_id": search_id, "user_id": user_id})
            )
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessSearch", operation="get_for_user", message=str(e)
            ) from e

    async def list_for_user(
        self,
        user_id: UUID,
        params: ListQueryParams,
        status: Optional[SearchStatus] = None,
    ) -> Tuple[List[BusinessSearch], int]:
        """The caller's searches, newest first by default."""
        try:
            query: dict[str, Any] = {"user_id": user_id}
            if status is not None:
                query["status"] = status.value
            term = params.normalized_search
            if term:
                query["$or"] = [
                    {"keyword": contains_ci(term)},
                    {"location_label": contains_ci(term)},
                ]
            total = self.collection.count_documents(query)
            field = resolve_sort_column(params.sort, SORTABLE, "created_at")
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
                entity_name="BusinessSearch", operation="list_for_user", message=str(e)
            ) from e

    async def recent_for_user(
        self, user_id: UUID, limit: int = 5
    ) -> List[BusinessSearch]:
        """The caller's latest searches."""
        try:
            cursor = (
                self.collection.find({"user_id": user_id})
                .sort([("created_at", DESCENDING), ("_id", ASCENDING)])
                .limit(limit)
            )
            return self.load_many(cursor)
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessSearch",
                operation="recent_for_user",
                message=str(e),
            ) from e

    async def count_for_user(self, user_id: UUID) -> int:
        """How many searches the caller has run."""
        try:
            return int(self.collection.count_documents({"user_id": user_id}))
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessSearch", operation="count_for_user", message=str(e)
            ) from e

    async def requests_since(
        self, since: datetime, user_id: Optional[UUID] = None
    ) -> int:
        """Places requests spent since a moment — one user's, or everyone's."""
        try:
            match: dict[str, Any] = {"created_at": {"$gte": since}}
            if user_id is not None:
                match["user_id"] = user_id
            rows = list(
                self.collection.aggregate(
                    [
                        {"$match": match},
                        {"$group": {"_id": None, "total": {"$sum": "$api_requests"}}},
                    ]
                )
            )
            return int(rows[0]["total"]) if rows else 0
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessSearch", operation="requests_since", message=str(e)
            ) from e

    async def count_since(self, since: datetime) -> int:
        """Searches started since a moment, by anyone (admin overview)."""
        try:
            return int(self.collection.count_documents({"created_at": {"$gte": since}}))
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessSearch", operation="count_since", message=str(e)
            ) from e

    async def has_active(self, user_id: UUID) -> bool:
        """Whether the caller has a search queued or running."""
        try:
            return (
                self.collection.count_documents(
                    {"user_id": user_id, "status": {"$in": _ACTIVE}}, limit=1
                )
                > 0
            )
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessSearch", operation="has_active", message=str(e)
            ) from e

    async def claim(self, search_id: UUID, now: datetime) -> bool:
        """Move a QUEUED search to RUNNING, atomically.

        One update with the status in its filter, as the collection module
        claims a source: a search handed to two workers is run by one.
        """
        try:
            result = self.collection.update_one(
                {"_id": search_id, "status": SearchStatus.QUEUED.value},
                {"$set": {"status": SearchStatus.RUNNING.value, "started_at": now}},
            )
            return result.modified_count > 0
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessSearch", operation="claim", message=str(e)
            ) from e

    async def fail_stale(self, before: datetime, now: datetime) -> int:
        """Mark searches stuck in QUEUED/RUNNING since before ``before`` failed.

        A restart kills the worker thread mid-search; without this the screen
        would show "running" forever.
        """
        try:
            result = self.collection.update_many(
                {"status": {"$in": _ACTIVE}, "created_at": {"$lt": before}},
                {
                    "$set": {
                        "status": SearchStatus.FAILED.value,
                        "finished_at": now,
                        "error_message": "The search was interrupted (the server "
                        "restarted). Run it again.",
                    }
                },
            )
            return int(result.modified_count)
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessSearch", operation="fail_stale", message=str(e)
            ) from e

    async def delete_for_user(self, user_id: UUID, search_id: UUID) -> bool:
        """Delete the caller's search and its result links (not the leads).

        MongoDB has no foreign keys, so what the SQL schema did on delete is
        done here: results are deleted (CASCADE), and exports and saved leads
        that pointed at the search keep their row with ``search_id`` nulled
        (SET NULL).
        """
        try:
            result = self.collection.delete_one({"_id": search_id, "user_id": user_id})
            if not result.deleted_count:
                return False
            db = self.session
            db.collection(BusinessSearchResult).delete_many({"search_id": search_id})
            for model in (LeadExport, SavedLead):
                db.collection(model).update_many(
                    {"search_id": search_id}, {"$set": {"search_id": None}}
                )
            return True
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessSearch",
                operation="delete_for_user",
                message=str(e),
            ) from e
