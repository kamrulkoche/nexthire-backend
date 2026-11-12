"""Use cases behind the notification bell, plus the one other modules call to
raise notifications (``NotifyUseCase``)."""

from typing import List, Optional, Sequence, Tuple
from uuid import UUID

from src.modules.user.infrastructure.repositories.user_repository import UserRepository
from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.not_found_error import NotFoundError
from src.shared.domain.text import clip
from src.shared.domain.time import utc_now
from src.shared.infrastructure.database import MongoSession

from ...domain.entities.notification import Notification
from ...domain.enums.notification_kind import NotificationKind
from ...infrastructure.repositories.notification_repository import (
    NotificationRepository,
)
from ..schemas.notification_schema import (
    MarkedReadSchema,
    NotificationSchema,
    UnreadCountSchema,
)


class _NotificationUseCase:
    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.session = session
        self.repository = NotificationRepository(session)


class ListNotificationsUseCase(_NotificationUseCase):
    """The caller's notifications."""

    async def execute(
        self, user_id: UUID, params: ListQueryParams, *, unread_only: bool = False
    ) -> Tuple[List[NotificationSchema], int]:
        """List notifications, newest first."""
        rows, total = await self.repository.list_for_user(
            user_id, params, unread_only=unread_only
        )
        return [NotificationSchema.model_validate(row) for row in rows], total


class UnreadCountUseCase(_NotificationUseCase):
    """The bell's badge."""

    async def execute(self, user_id: UUID) -> UnreadCountSchema:
        """Count the caller's unread notifications."""
        return UnreadCountSchema(unread=await self.repository.unread_count(user_id))


class MarkReadUseCase(_NotificationUseCase):
    """Mark one notification read."""

    async def execute(self, user_id: UUID, notification_id: UUID) -> NotificationSchema:
        """Mark it read. Idempotent: a read one keeps its first read time.

        Raises:
            NotFoundError: If the caller has no notification with this id
        """
        row = await self.repository.get_for_user(user_id, notification_id)
        if row is None:
            raise NotFoundError(entity_name="Notification", entity_id=notification_id)
        if row.read_at is None:
            row.read_at = utc_now()
            self.session.add(row)
            self.session.commit()
            self.session.refresh(row)
        return NotificationSchema.model_validate(row)


class MarkAllReadUseCase(_NotificationUseCase):
    """Mark everything read."""

    async def execute(self, user_id: UUID) -> MarkedReadSchema:
        """Mark every unread notification of the caller's read."""
        return MarkedReadSchema(
            marked=await self.repository.mark_all_read(user_id, utc_now())
        )


class NotifyUseCase(_NotificationUseCase):
    """Raise notifications. Called by other modules, never by a route."""

    async def to_users(
        self,
        user_ids: Sequence[UUID],
        *,
        kind: NotificationKind,
        title: str,
        body: str = "",
        link: Optional[str] = None,
    ) -> int:
        """Send one notification to each user.

        Args:
            user_ids: Recipients
            kind: What it is about
            title: Headline, clipped to the column
            body: Detail, clipped to the column
            link: An in-app path starting with "/"; anything else is dropped

        Returns:
            How many were created
        """
        safe_link = (
            link
            if link and link.startswith("/") and not link.startswith("//")
            else None
        )
        rows = [
            Notification(
                user_id=user_id,
                kind=kind,
                title=clip(title, 200) or "Notification",
                body=clip(body, 1000) or "",
                link=safe_link,
            )
            for user_id in dict.fromkeys(user_ids)
        ]
        await self.repository.add_all(rows)
        return len(rows)

    async def to_admins(
        self,
        *,
        kind: NotificationKind,
        title: str,
        body: str = "",
        link: Optional[str] = None,
    ) -> int:
        """Send one notification to every active admin."""
        admin_ids = await UserRepository(self.session).active_admin_ids()
        return await self.to_users(
            admin_ids, kind=kind, title=title, body=body, link=link
        )
