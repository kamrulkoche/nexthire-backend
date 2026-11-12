"""A business as the Places API returned it, before it is stored."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class PlaceRecord:
    """One place from Text Search or Place Details, already flattened.

    Every field but ``place_id`` may be missing: Google omits what a business
    has not published, and this module never fills a gap with a guess.
    """

    place_id: str
    name: Optional[str] = None
    primary_category: Optional[str] = None
    primary_type: Optional[str] = None
    types: List[str] = field(default_factory=list)
    rating: Optional[float] = None
    review_count: Optional[int] = None
    formatted_address: Optional[str] = None
    phone_display: Optional[str] = None
    phone_international: Optional[str] = None
    website_uri: Optional[str] = None
    google_maps_uri: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    opening_hours: List[str] = field(default_factory=list)
    business_status: Optional[str] = None
