"""
LeadFinderSettings entity — the admin's switches for the Lead Finder product.
"""

from pydantic import Field

from src.shared.domain.entities.audited_entity import AuditedEntity


class LeadFinderSettings(AuditedEntity):
    """
    One document, holding what an admin may change without a deploy.

    A collection rather than environment variables because the requirement is that
    an ADMIN turns registration on and off. The document is created on first read
    with defaults from settings (`LEAD_DAILY_REQUEST_QUOTA`,
    `LEAD_MAX_REQUESTS_PER_SEARCH`); there is never more than one, because
    the repository only ever reads the oldest.

    Attributes:
        registration_enabled: Whether `/auth/lead-finder/register` accepts
            new accounts. Off by default: an admin opts in.
        daily_request_quota: Places API requests ONE lead finder may spend
            per UTC day, across all their searches.
        max_requests_per_search: Places API requests one search may spend.
            An "all of Bangladesh" search fans out over 64 districts at up to
            three pages each, so this is what bounds its cost.

    Collection: lead_finder_settings
    """

    __collection__ = "lead_finder_settings"

    registration_enabled: bool = Field(default=False)

    daily_request_quota: int = Field(default=300, ge=0)

    max_requests_per_search: int = Field(default=90, ge=1)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<LeadFinderSettings(registration_enabled={self.registration_enabled}, "
            f"daily_request_quota={self.daily_request_quota})>"
        )


__all__ = ["LeadFinderSettings"]
