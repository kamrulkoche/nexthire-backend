"""The filters a lead list can be narrowed by."""

from dataclasses import dataclass, field
from typing import List, Literal, Optional
from uuid import UUID

#: "with" / "without" a website or phone; None = either.
Presence = Optional[Literal["with", "without"]]

#: Sort keys a lead list accepts. Anything else falls back to the default
#: (potential leads first, then Google's relevance order).
LEAD_SORTS = ("relevance", "name", "rating", "review_count", "district")


@dataclass(frozen=True)
class LeadFilter:
    """Every way a lead list can be narrowed. All combine with AND.

    Attributes:
        search_id: One search's results; None = every search of the user's
        website: Has a website or not
        phone: Has a phone number or not
        min_rating: Google rating at least this (0-5)
        min_reviews: Review count at least this
        division: Division name the search found it under
        district: District name the search found it under
        category: Substring of Google's category ("hospital")
        text: Substring of name, address or phone
        saved: Only leads the user saved (True), only unsaved (False)
        lead_ids: Only these (a selection being exported)
        duplicate_phone_only: Only leads whose number another lead shares
    """

    search_id: Optional[UUID] = None
    website: Presence = None
    phone: Presence = None
    min_rating: Optional[float] = None
    min_reviews: Optional[int] = None
    division: Optional[str] = None
    district: Optional[str] = None
    category: Optional[str] = None
    text: Optional[str] = None
    saved: Optional[bool] = None
    lead_ids: List[UUID] = field(default_factory=list)
    duplicate_phone_only: bool = False

    def as_dict(self) -> dict:
        """The active filters, for export history. Empty values omitted."""
        values = {
            "search_id": str(self.search_id) if self.search_id else None,
            "website": self.website,
            "phone": self.phone,
            "min_rating": self.min_rating,
            "min_reviews": self.min_reviews,
            "division": self.division,
            "district": self.district,
            "category": self.category,
            "text": self.text,
            "saved": self.saved,
            "selected": len(self.lead_ids) or None,
            "duplicate_phone_only": self.duplicate_phone_only or None,
        }
        return {k: v for k, v in values.items() if v not in (None, "")}
