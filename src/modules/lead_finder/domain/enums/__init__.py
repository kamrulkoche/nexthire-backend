"""Lead Finder domain enums."""

from enum import Enum


class SearchStatus(str, Enum):
    """Where a business search is in its life.

    - QUEUED: created, waiting for the background worker
    - RUNNING: the worker is calling the Places API
    - COMPLETED: every location was searched
    - PARTIAL: stopped early (request cap reached) or some locations failed,
      but results were stored
    - FAILED: nothing could be fetched (no key, API refused, every call failed)
    """

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"

    @property
    def is_finished(self) -> bool:
        """Whether the worker is done with this search."""
        return self in (
            SearchStatus.COMPLETED,
            SearchStatus.PARTIAL,
            SearchStatus.FAILED,
        )


class LeadStatus(str, Enum):
    """A saved lead's place in the user's outreach pipeline."""

    NEW = "new"
    CONTACTED = "contacted"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    CONVERTED = "converted"


class ExportFormat(str, Enum):
    """File formats an export can be produced in."""

    CSV = "csv"
    XLSX = "xlsx"
    PDF = "pdf"


__all__ = ["ExportFormat", "LeadStatus", "SearchStatus"]
