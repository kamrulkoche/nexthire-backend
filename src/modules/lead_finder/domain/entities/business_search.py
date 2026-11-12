"""
BusinessSearch entity — one search a lead finder ran.
"""

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from src.shared.domain.entities.base_entity import BaseEntity

from ..enums import SearchStatus


class BusinessSearch(BaseEntity):
    """
    A keyword searched over one or more locations, and what it found.

    The search itself is the user's own data (what they typed, where, when),
    so it is kept for the history screen. What Google returned lives in
    ``business_leads``, linked through ``business_search_results``.

    Progress fields (``completed_targets`` of ``total_targets``) are written
    by the background worker as it goes, so the screen can show a progress
    bar while a large search runs.

    The four counters are a SNAPSHOT taken when the search finished, for the
    history list. They are the user's numbers, not Google content, and so
    survive the content purge.

    Deleting a search deletes its results and nulls ``search_id`` on exports
    and saved leads (see ``BusinessSearchRepository.delete_for_user``).

    Collection: business_searches
    """

    __collection__ = "business_searches"
    __indexes__ = [
        IndexModel(
            [("user_id", ASCENDING), ("created_at", DESCENDING)],
            name="ix_business_searches_user_created",
        ),
        IndexModel([("status", ASCENDING)], name="ix_business_searches_status"),
    ]

    user_id: UUID

    keyword: str = Field(max_length=120)

    #: The preset category key the keyword came from (``hospital``), or null
    #: for a custom keyword.
    category: Optional[str] = Field(default=None, max_length=60)

    #: The selected locations: ``[{"code": "dhaka/dhaka/savar", "label": ...,
    #: "level": "upazila"}]``. An empty list means all of Bangladesh.
    locations: List[Any] = Field(default_factory=list)

    #: Human summary of ``locations`` for lists ("Savar, Dhaka +2 more").
    location_label: str = Field(max_length=300)

    status: SearchStatus = Field(default=SearchStatus.QUEUED)

    total_targets: int = Field(default=0)
    completed_targets: int = Field(default=0)
    failed_targets: int = Field(default=0)

    #: Places API requests this search spent. Summed per day for the quota.
    api_requests: int = Field(default=0)

    total_results: int = Field(default=0)
    #: No website AND a phone number — the "potential leads" rule.
    leads_found: int = Field(default=0)
    with_phone: int = Field(default=0)
    without_website: int = Field(default=0)

    error_message: Optional[str] = Field(default=None, max_length=500)

    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)

    def __repr__(self) -> str:
        """String representation."""
        return f"<BusinessSearch(id='{self.id}', keyword='{self.keyword}', status='{self.status}')>"
