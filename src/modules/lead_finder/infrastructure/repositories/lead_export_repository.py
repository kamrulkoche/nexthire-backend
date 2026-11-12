"""Export history repository. Scoped to the caller like every lead collection."""

from typing import List, Tuple, Type
from uuid import UUID

from pymongo import ASCENDING, DESCENDING

from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.repository_error import RepositoryError
from src.shared.infrastructure.base_repository import BaseRepository
from src.shared.infrastructure.database import MongoSession

from ...domain.entities.lead_export import LeadExport


class LeadExportRepository(BaseRepository[LeadExport]):
    """Repository for LeadExport database operations."""

    def __init__(self, session: MongoSession, model: Type[LeadExport] = LeadExport):
        """Initialize the export repository."""
        super().__init__(session, model)

    async def list_for_user(
        self, user_id: UUID, params: ListQueryParams
    ) -> Tuple[List[LeadExport], int]:
        """The caller's exports, newest first."""
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
                entity_name="LeadExport", operation="list_for_user", message=str(e)
            ) from e

    async def count_for_user(self, user_id: UUID) -> int:
        """How many exports the caller has made."""
        try:
            return int(self.collection.count_documents({"user_id": user_id}))
        except Exception as e:
            raise RepositoryError(
                entity_name="LeadExport", operation="count_for_user", message=str(e)
            ) from e
