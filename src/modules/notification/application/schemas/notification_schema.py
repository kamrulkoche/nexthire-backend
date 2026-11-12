"""Notification Pydantic schemas. Mirrored in `src/interface/seeker.interface.ts` (`INotification`)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ...domain.enums.notification_kind import NotificationKind


class NotificationSchema(BaseModel):
    """A notification in the bell or on the Notifications screen."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: NotificationKind
    title: str
    body: str
    link: Optional[str] = None
    read_at: Optional[datetime] = None
    created_at: datetime


class UnreadCountSchema(BaseModel):
    """The bell's badge."""

    unread: int = 0


class MarkedReadSchema(BaseModel):
    """How many notifications a mark-all-read changed."""

    marked: int = 0
