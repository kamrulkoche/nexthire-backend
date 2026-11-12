"""Notification module dependencies for dependency injection."""

from fastapi import Depends
from src.shared.infrastructure.database import MongoSession

from src.shared.infrastructure.database import get_db

from ..application.use_cases.notification_use_cases import (
    ListNotificationsUseCase,
    MarkAllReadUseCase,
    MarkReadUseCase,
    UnreadCountUseCase,
)


def get_list_notifications_use_case(
    db: MongoSession = Depends(get_db),
) -> ListNotificationsUseCase:
    """Get the notification list use case with the shared DB session."""
    return ListNotificationsUseCase(db)


def get_unread_count_use_case(db: MongoSession = Depends(get_db)) -> UnreadCountUseCase:
    """Get the unread-count use case with the shared DB session."""
    return UnreadCountUseCase(db)


def get_mark_read_use_case(db: MongoSession = Depends(get_db)) -> MarkReadUseCase:
    """Get the mark-read use case with the shared DB session."""
    return MarkReadUseCase(db)


def get_mark_all_read_use_case(
    db: MongoSession = Depends(get_db),
) -> MarkAllReadUseCase:
    """Get the mark-all-read use case with the shared DB session."""
    return MarkAllReadUseCase(db)
