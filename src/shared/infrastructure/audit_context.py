"""
Audit context service for thread-local storage of the current user ID.

Provides thread-safe storage for the acting user during request processing so
repositories can stamp ``created_by`` / ``updated_by`` without threading the ID
through every method signature.

Set by the auth dependency after a token is validated; cleared by
``AuditContextMiddleware`` when the request ends.
"""

import threading
from typing import Optional
from uuid import UUID

# Thread-local storage for audit context
_audit_context = threading.local()


def set_current_user(user_id: UUID) -> None:
    """
    Set the current user ID in thread-local context.

    Called after authentication succeeds.

    Args:
        user_id: Database UUID of the authenticated user
    """
    _audit_context.user_id = user_id


def get_current_user_id() -> Optional[UUID]:
    """
    Get the current user ID from thread-local context.

    Returns:
        The acting user's UUID, or None in an anonymous/system context
        (public routes, startup bootstrap, scripts).
    """
    return getattr(_audit_context, "user_id", None)


def clear_current_user() -> None:
    """
    Clear the audit context.

    In an async server multiple requests share a thread, so a stale value would
    leak one user's identity into another user's writes.
    """
    if hasattr(_audit_context, "user_id"):
        delattr(_audit_context, "user_id")
