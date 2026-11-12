"""Notification kind enum."""

from enum import Enum


class NotificationKind(str, Enum):
    """
    What a notification is about. The frontend picks an icon per kind.

    - NEW_MATCHES: a collection run found jobs that score well for a seeker
    - RUN_FAILED: a source could not be read (admins only)
    - SYSTEM: anything else
    """

    NEW_MATCHES = "new_matches"
    RUN_FAILED = "run_failed"
    SYSTEM = "system"
