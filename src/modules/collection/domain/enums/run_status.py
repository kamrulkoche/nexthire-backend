"""Collection run status enum."""

from enum import Enum


class RunStatus(str, Enum):
    """
    How a collection run ended — or that it has not yet.

    - RUNNING: claimed and in progress
    - SUCCEEDED: fetched and stored everything it got
    - PARTIAL: fetched, but some postings could not be stored (bad rows skipped)
    - FAILED: the source could not be read at all; nothing changed

    Also stored on the source as ``last_run_status``, so the Sources screen
    shows health without a join.
    """

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"

    @classmethod
    def all_statuses(cls) -> list[str]:
        """Return all valid status values."""
        return [status.value for status in cls]
