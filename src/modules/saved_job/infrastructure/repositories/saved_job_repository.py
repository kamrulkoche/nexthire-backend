"""
Saved job repository.

Every method takes the caller's ``user_id`` and filters on it. There is no
"get any saved job by id" — a seeker can only ever reach their own documents,
because no query here can return anyone else's.
"""

from typing import Iterable, List, Optional, Set, Tuple, Type
from uuid import UUID

from pymongo import ASCENDING, DESCENDING

from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.repository_error import RepositoryError
from src.shared.infrastructure.base_repository import BaseRepository
from src.shared.infrastructure.database import MongoSession

from ...domain.entities.saved_job import SavedJob


class SavedJobRepository(BaseRepository[SavedJob]):
    """Repository for SavedJob database operations."""

    def __init__(self, session: MongoSession, model: Type[SavedJob] = SavedJob):
        """Initialize the saved job repository."""
        super().__init__(session, model)

    async def get_for_user(self, user_id: UUID, job_id: UUID) -> Optional[SavedJob]:
        """The caller's bookmark on this job, or None."""
        try:
            return self.load(
                self.collection.find_one({"user_id": user_id, "job_id": job_id})
            )
        except Exception as e:
            raise RepositoryError(
                entity_name="SavedJob", operation="get_for_user", message=str(e)
            ) from e

    async def list_for_user(
        self, user_id: UUID, params: ListQueryParams
    ) -> Tuple[List[SavedJob], int]:
        """The caller's bookmarks, newest first."""
        try:
            query = {"user_id": user_id}
            total = self.collection.count_documents(query)
            cursor = (
                self.collection.find(query)
                .sort([("created_at", DESCENDING), ("_id", ASCENDING)])
                .skip(params.offset)
                .limit(params.limit)
            )
            return self.load_many(cursor), int(total)
        except Exception as e:
            raise RepositoryError(
                entity_name="SavedJob", operation="list_for_user", message=str(e)
            ) from e

    async def saved_job_ids(self, user_id: UUID, job_ids: Iterable[UUID]) -> Set[UUID]:
        """Which of these jobs the caller has saved — to mark cards in a list."""
        ids = list(set(job_ids))
        if not ids:
            return set()
        try:
            cursor = self.collection.find(
                {"user_id": user_id, "job_id": {"$in": ids}}, {"job_id": 1}
            )
            return {doc["job_id"] for doc in cursor}
        except Exception as e:
            raise RepositoryError(
                entity_name="SavedJob", operation="saved_job_ids", message=str(e)
            ) from e

    async def delete_for_user(self, user_id: UUID, job_id: UUID) -> bool:
        """Remove the caller's bookmark. Returns whether one existed."""
        try:
            result = self.collection.delete_one({"user_id": user_id, "job_id": job_id})
            return result.deleted_count > 0
        except Exception as e:
            raise RepositoryError(
                entity_name="SavedJob", operation="delete_for_user", message=str(e)
            ) from e

    async def count_for_user(self, user_id: UUID) -> int:
        """How many jobs the caller has saved."""
        try:
            return int(self.collection.count_documents({"user_id": user_id}))
        except Exception as e:
            raise RepositoryError(
                entity_name="SavedJob", operation="count_for_user", message=str(e)
            ) from e
