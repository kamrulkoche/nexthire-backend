"""
BusinessLead entity — one business found through the Places API.
"""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import Field
from pymongo import ASCENDING, IndexModel

from src.shared.domain.entities.audited_entity import AuditedEntity

#: Every field holding content that came from Google. The content purge
#: (``BusinessLeadRepository.purge_expired_content``) clears exactly these;
#: the place ID, the location the search attributed the business to, and the
#: user's own data in other collections are kept.
GOOGLE_CONTENT_FIELDS: tuple[str, ...] = (
    "name",
    "primary_category",
    "primary_type",
    "types",
    "rating",
    "review_count",
    "formatted_address",
    "phone_display",
    "phone_international",
    "phone_normalized",
    "website_uri",
    "google_maps_uri",
    "latitude",
    "longitude",
    "opening_hours",
    "business_status",
)


class BusinessLead(AuditedEntity):
    """
    A business, unique by its Google place ID.

    De-duplication: one document per ``place_id`` across every user and
    search. Two searches that find the same hospital point at the same
    document through ``business_search_results``; a later search refreshes its
    content.

    **Storage policy.** Google Maps Platform terms allow a place ID to be
    stored indefinitely, but other Places content only temporarily. So every
    Google-sourced field is nullable and carries an expiry
    (``content_expires_at``, ``LEAD_CONTENT_TTL_DAYS`` after ``fetched_at``).
    The scheduler wipes expired content (``content_purged = True``); a
    "Refresh" re-reads it from Place Details. ``GOOGLE_CONTENT_FIELDS`` is the
    list the purge clears.

    ``has_website`` / ``has_phone`` are derived from that content at write time
    (so the default lead filter is an indexed boolean test) and are cleared
    with it.

    Phone numbers are stored three ways: Google's national format for display
    (``phone_display``), its international format, and an E.164 normalization
    (``phone_normalized``) used for duplicate detection. A number is never
    invented: no number from Google means all three are null.

    ``division`` / ``district`` / ``upazila`` / ``area`` are the location the
    SEARCH attributed the business to (the target it was found under), not
    parsed from Google's address. They are this service's own data.

    Collection: business_leads
    """

    __collection__ = "business_leads"
    __indexes__ = [
        IndexModel(
            [("place_id", ASCENDING)], unique=True, name="uq_business_leads_place_id"
        ),
        IndexModel(
            [("has_website", ASCENDING), ("has_phone", ASCENDING)],
            name="ix_business_leads_lead_flags",
        ),
        IndexModel(
            [("content_expires_at", ASCENDING)],
            name="ix_business_leads_content_expires",
        ),
        IndexModel(
            [("phone_normalized", ASCENDING)], name="ix_business_leads_phone_normalized"
        ),
        IndexModel([("name", ASCENDING)], name="ix_business_leads_name"),
        IndexModel(
            [("division", ASCENDING), ("district", ASCENDING)],
            name="ix_business_leads_division_district",
        ),
    ]

    place_id: str = Field(max_length=255)

    name: Optional[str] = Field(default=None, max_length=300)
    primary_category: Optional[str] = Field(default=None, max_length=120)
    primary_type: Optional[str] = Field(default=None, max_length=80)
    types: Optional[List[str]] = Field(default=None)

    rating: Optional[float] = Field(default=None)
    review_count: Optional[int] = Field(default=None)

    formatted_address: Optional[str] = Field(default=None, max_length=500)

    phone_display: Optional[str] = Field(default=None, max_length=40)
    phone_international: Optional[str] = Field(default=None, max_length=40)
    phone_normalized: Optional[str] = Field(default=None, max_length=20)

    website_uri: Optional[str] = Field(default=None, max_length=1000)
    google_maps_uri: Optional[str] = Field(default=None, max_length=1000)

    latitude: Optional[float] = Field(default=None)
    longitude: Optional[float] = Field(default=None)

    #: Google's weekday descriptions ("Monday: 9:00 AM – 5:00 PM").
    opening_hours: Optional[List[Any]] = Field(default=None)

    business_status: Optional[str] = Field(default=None, max_length=40)

    has_website: bool = Field(default=False)
    has_phone: bool = Field(default=False)

    division: Optional[str] = Field(default=None, max_length=80)
    district: Optional[str] = Field(default=None, max_length=80)
    upazila: Optional[str] = Field(default=None, max_length=80)
    area: Optional[str] = Field(default=None, max_length=120)

    fetched_at: Optional[datetime] = Field(default=None)
    content_expires_at: Optional[datetime] = Field(default=None)
    content_purged: bool = Field(default=False)

    @property
    def is_potential_lead(self) -> bool:
        """No website, but a phone number to call: the default lead rule."""
        return self.has_phone and not self.has_website

    def __repr__(self) -> str:
        """String representation."""
        return f"<BusinessLead(place_id='{self.place_id}', name='{self.name}')>"
