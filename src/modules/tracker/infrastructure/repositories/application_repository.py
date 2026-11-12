"""Job application repository. Every method is scoped to the caller's ``user_id``."""

from typing import Any, Dict, List, Optional, Tuple, Type
from uuid import UUID

from pymongo import ASCENDING, DESCENDING

from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.repository_error import RepositoryError
from src.shared.infrastructure.base_repository import BaseRepository
from src.shared.infrastructure.database import MongoSession
from src.shared.infrastructure.ordering import contains_ci, resolve_sort_column

from ...domain.entities.job_application import JobApplication
from ...domain.enums.application_status import ApplicationStatus

#: Fields the tracker may sort by — see `resolve_sort_column`.
SORTABLE = {
    "updated_at",
    "created_at",
    "applied_on",
    "next_step_at",
    "company",
    "status",
}

DEFAULT_SORT = "updated_at"


class ApplicationRepository(BaseRepository[JobApplication]):
    """Repository for JobApplication database operations."""

    def __init__(
        self, session: MongoSession, model: Type[JobApplication] = JobApplication
    ):
        """Initialize the application repository."""
        super().__init__(session, model)

    def _mine(self, user_id: UUID) -> dict[str, Any]:
        return {"user_id": user_id, "is_active": True}

    async def get_for_user(
        self, user_id: UUID, application_id: UUID
    ) -> Optional[JobApplication]:
        """One of the caller's live applications, or None."""
        try:
            return self.load(
                self.collection.find_one({"_id": application_id, **self._mine(user_id)})
            )
        except Exception as e:
            raise RepositoryError(
                entity_name="JobApplication", operation="get_for_user", message=str(e)
            ) from e

    async def find_for_job(
        self, user_id: UUID, job_id: UUID
    ) -> Optional[JobApplication]:
        """The caller's live application to this job, if they track one."""
        try:
            return self.load(
                self.collection.find_one({"job_id": job_id, **self._mine(user_id)})
            )
        except Exception as e:
            raise RepositoryError(
                entity_name="JobApplication", operation="find_for_job", message=str(e)
            ) from e

    async def list_for_user(
        self,
        user_id: UUID,
        params: ListQueryParams,
        *,
        status: Optional[ApplicationStatus] = None,
    ) -> Tuple[List[JobApplication], int]:
        """The caller's applications; most recently changed first by default."""
        try:
            query = self._mine(user_id)
            if status is not None:
                query["status"] = status.value
            term = params.normalized_search
            if term:
                query["$or"] = [
                    {"title": contains_ci(term)},
                    {"company": contains_ci(term)},
                    {"notes": contains_ci(term)},
                ]
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
                entity_name="JobApplication", operation="list_for_user", message=str(e)
            ) from e

    async def counts_by_status(self, user_id: UUID) -> Dict[str, int]:
        """``{status: count}`` over the caller's live applications."""
        try:
            rows = self.collection.aggregate(
                [
                    {"$match": self._mine(user_id)},
                    {"$group": {"_id": "$status", "count": {"$sum": 1}}},
                ]
            )
            return {str(row["_id"]): int(row["count"]) for row in rows}
        except Exception as e:
            raise RepositoryError(
                entity_name="JobApplication",
                operation="counts_by_status",
                message=str(e),
            ) from e
