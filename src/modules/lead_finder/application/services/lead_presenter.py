"""Turning lead rows into what the screens show.

One place that decorates a lead for the CALLER: whether they saved it (and at
what status), and whether its number is shared by another lead in the same
list (duplicate detection). Every lead-returning use case goes through it, so
a card looks the same on the search screen, the phone list and the dashboard.
"""

from typing import Iterable, List, Optional, Set
from uuid import UUID

from src.shared.infrastructure.database import MongoSession

from ...domain.entities.business_lead import BusinessLead
from ...domain.entities.business_search import BusinessSearch
from ...infrastructure.repositories.business_lead_repository import (
    BusinessLeadRepository,
)
from ...infrastructure.repositories.saved_lead_repository import SavedLeadRepository
from ..schemas.lead_finder_schema import LeadSchema, SearchSchema


class LeadPresenter:
    """Builds ``LeadSchema`` rows for one user."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.leads = BusinessLeadRepository(session)
        self.saved = SavedLeadRepository(session)

    async def present(
        self,
        user_id: UUID,
        rows: List[BusinessLead],
        *,
        duplicate_phones: Optional[Set[str]] = None,
    ) -> List[LeadSchema]:
        """Decorate rows for the caller.

        Args:
            user_id: The caller
            rows: Leads already scoped to the caller
            duplicate_phones: Numbers shared within the list's scope; None
                skips duplicate marking
        """
        saved = await self.saved.by_lead_ids(
            user_id, (row.id for row in rows if row.id)
        )
        duplicates = duplicate_phones or set()
        result = []
        for row in rows:
            assert row.id is not None
            saved_row = saved.get(row.id)
            result.append(
                lead_schema(
                    row,
                    is_duplicate_phone=bool(
                        row.phone_normalized and row.phone_normalized in duplicates
                    ),
                    saved_lead_id=saved_row.id if saved_row else None,
                    saved_status=saved_row.status if saved_row else None,
                )
            )
        return result


def lead_schema(
    row: BusinessLead,
    *,
    is_duplicate_phone: bool = False,
    saved_lead_id: Optional[UUID] = None,
    saved_status: Optional[object] = None,
) -> LeadSchema:
    """One lead as the API returns it."""
    assert row.id is not None
    return LeadSchema(
        id=row.id,
        place_id=row.place_id,
        name=row.name,
        category=row.primary_category,
        types=list(row.types or []),
        rating=row.rating,
        review_count=row.review_count,
        address=row.formatted_address,
        phone=row.phone_display or row.phone_international,
        phone_international=row.phone_international,
        phone_normalized=row.phone_normalized,
        website=row.website_uri,
        google_maps_url=row.google_maps_uri,
        latitude=row.latitude,
        longitude=row.longitude,
        opening_hours=[str(h) for h in (row.opening_hours or [])],
        business_status=row.business_status,
        division=row.division,
        district=row.district,
        upazila=row.upazila,
        area=row.area,
        has_website=row.has_website,
        has_phone=row.has_phone,
        is_potential_lead=row.is_potential_lead,
        is_duplicate_phone=is_duplicate_phone,
        saved_lead_id=saved_lead_id,
        saved_status=saved_status,  # type: ignore[arg-type]
        content_expired=row.content_purged,
        fetched_at=row.fetched_at,
    )


def search_schema(row: BusinessSearch) -> SearchSchema:
    """One search as the API returns it."""
    return SearchSchema.model_validate(row)


def search_schemas(rows: Iterable[BusinessSearch]) -> List[SearchSchema]:
    """Several searches."""
    return [search_schema(row) for row in rows]
