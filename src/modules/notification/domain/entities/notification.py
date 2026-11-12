"""
Notification entity — one message in a user's bell.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from src.shared.domain.entities.base_entity import BaseEntity

from ..enums.notification_kind import NotificationKind


class Notification(BaseEntity):
    """
    A notification for one user.

    STORED, unlike hgs-backend's bell, which derives its items from other
    tables on every request. HGS can do that because it has one audience and
    every notification is "there is an unhandled row in table X". Here the
    events come from background work (a run found matches for you; a source
    failed) and there is nothing to derive them from afterwards.

    ``link`` is an in-app path (``/app/recommendations``), never an absolute
    URL, so a notification cannot send someone off-site.

    Collection: notifications
    """

    __collection__ = "notifications"
    __indexes__ = [
        IndexModel(
            [("user_id", ASCENDING), ("created_at", DESCENDING)],
            name="ix_notifications_user_created",
        ),
    ]

    user_id: UUID

    kind: NotificationKind

    title: str = Field(max_length=200)

    body: str = Field(default="", max_length=1000)

    link: Optional[str] = Field(default=None, max_length=300)

    read_at: Optional[datetime] = None

    def __repr__(self) -> str:
        """String representation of Notification."""
        return f"<Notification(user_id='{self.user_id}', kind='{self.kind}')>"
