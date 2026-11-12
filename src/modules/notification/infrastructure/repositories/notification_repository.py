"""Notification repository. Seeker-facing methods filter on ``user_id``."""

from datetime import datetime
from typing import Any, List, Optional, Sequence, Tuple, Type
from uuid import UUID

from pymongo import ASCENDING, DESCENDING

from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.repository_error import RepositoryError
from src.shared.infrastructure.base_repository import BaseRepository
from src.shared.infrastructure.database import MongoSession

from ...domain.entities.notification import Notification


class NotificationRepository(BaseRepository[Notification]):
    """Repository for Notification database operations."""

    def __init__(self, session: MongoSession, model: Type[Notification] = Notification):
        """Initialize the notification repository."""
        super().__init__(session, model)

    async def list_for_user(
        self, user_id: UUID, params: ListQueryParams, *, unread_only: bool = False
    ) -> Tuple[List[Notification], int]:
        """The caller's notifications, newest first."""
        try:
            query: dict[str, Any] = {"user_id": user_id}
            if unread_only:
                query["read_at"] = None
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
                entity_name="Notification", operation="list_for_user", message=str(e)
            ) from e

    async def unread_count(self, user_id: UUID) -> int:
        """How many of the caller's notifications are unread."""
        try:
            return int(
                self.collection.count_documents({"user_id": user_id, "read_at": None})
            )
        except Exception as e:
            raise RepositoryError(
                entity_name="Notification", operation="unread_count", message=str(e)
            ) from e

    async def get_for_user(
        self, user_id: UUID, notification_id: UUID
    ) -> Optional[Notification]:
        """One of the caller's notifications, or None — never someone else's."""
        try:
            return self.load(
                self.collection.find_one({"_id": notification_id, "user_id": user_id})
            )
        except Exception as e:
            raise RepositoryError(
                entity_name="Notification", operation="get_for_user", message=str(e)
            ) from e

    async def mark_all_read(self, user_id: UUID, now: datetime) -> int:
        """Mark every unread notification of the caller's read."""
        try:
            result = self.collection.update_many(
                {"user_id": user_id, "read_at": None}, {"$set": {"read_at": now}}
            )
            return int(result.modified_count)
        except Exception as e:
            raise RepositoryError(
                entity_name="Notification", operation="mark_all_read", message=str(e)
            ) from e

    async def add_all(self, notifications: Sequence[Notification]) -> None:
        """Insert several notifications in one write."""
        if not notifications:
            return
        try:
            self.collection.insert_many([n.to_document() for n in notifications])
            for n in notifications:
                n._snapshot = n.to_document()
        except Exception as e:
            raise RepositoryError(
                entity_name="Notification", operation="add_all", message=str(e)
            ) from e
