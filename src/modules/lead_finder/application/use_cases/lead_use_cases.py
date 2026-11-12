"""Reading, filtering and refreshing leads, and the dashboard overview."""

from datetime import timedelta
from typing import List, Optional, Tuple
from uuid import UUID

from src.shared.infrastructure.database import MongoSession

from src.shared.domain.exceptions.not_found_error import NotFoundError
from src.shared.domain.time import utc_now
from src.shared.utils.config import settings

from ...domain.services.bangladesh_locations import location_tree
from ...domain.services.categories import category_list
from ...domain.value_objects.lead_filter import LEAD_SORTS, LeadFilter
from ...infrastructure.repositories.business_lead_repository import (
    BusinessLeadRepository,
)
from ...infrastructure.repositories.business_search_repository import (
    BusinessSearchRepository,
)
from ...infrastructure.repositories.lead_export_repository import LeadExportRepository
from ...infrastructure.repositories.saved_lead_repository import SavedLeadRepository
from ..schemas.lead_finder_schema import (
    CatalogSchema,
    LeadSchema,
    LeadSummarySchema,
    OverviewSchema,
    OverviewStatsSchema,
)
from ..services.lead_presenter import LeadPresenter, search_schemas
from .search_use_cases import GatewayFactory, QuotaService, default_gateway_factory


class GetCatalogUseCase:
    """Categories and the location tree for the search form."""

    def __init__(
        self, gateway_factory: GatewayFactory = default_gateway_factory
    ) -> None:
        """Inject the gateway factory (to report whether a key is set)."""
        self.gateway_factory = gateway_factory

    async def execute(self) -> CatalogSchema:
        """The catalog. Static apart from ``places_configured``."""
        return CatalogSchema.model_validate(
            {
                "categories": category_list(),
                "divisions": location_tree(),
                "places_configured": self.gateway_factory().is_configured,
            }
        )


class _LeadScopeMixin:
    searches: BusinessSearchRepository

    async def _check_search(self, user_id: UUID, search_id: Optional[UUID]) -> None:
        """A named search must be the caller's — a 404 otherwise, not an empty list."""
        if (
            search_id is not None
            and await self.searches.get_for_user(user_id, search_id) is None
        ):
            raise NotFoundError(entity_name="BusinessSearch", entity_id=search_id)


class ListLeadsUseCase(_LeadScopeMixin):
    """A filtered, sorted page of the caller's leads."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.leads = BusinessLeadRepository(session)
        self.searches = BusinessSearchRepository(session)
        self.presenter = LeadPresenter(session)

    async def execute(
        self,
        user_id: UUID,
        filters: LeadFilter,
        *,
        offset: int,
        limit: int,
        sort: Optional[str],
        order: str,
    ) -> Tuple[List[LeadSchema], int]:
        """Rows marked with saved state and duplicate numbers.

        Raises:
            NotFoundError: ``filters.search_id`` is not the caller's search
        """
        await self._check_search(user_id, filters.search_id)
        rows, total = await self.leads.list_for_user(
            user_id,
            filters,
            offset=offset,
            limit=limit,
            sort=sort if sort in LEAD_SORTS else None,
            order=order,
        )
        duplicates = await self.leads.duplicate_phones(user_id, filters.search_id)
        return (
            await self.presenter.present(user_id, rows, duplicate_phones=duplicates),
            total,
        )


class LeadSummaryUseCase(_LeadScopeMixin):
    """Counts and filter options for a lead list's scope."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.leads = BusinessLeadRepository(session)
        self.searches = BusinessSearchRepository(session)

    async def execute(
        self, user_id: UUID, search_id: Optional[UUID]
    ) -> LeadSummarySchema:
        """Raises NotFoundError for someone else's search."""
        await self._check_search(user_id, search_id)
        counts = await self.leads.counts(user_id, search_id)
        facets = await self.leads.facets(user_id, search_id)
        duplicates = await self.leads.duplicate_phones(user_id, search_id)
        return LeadSummarySchema(
            total=counts.total,
            without_website=counts.without_website,
            with_phone=counts.with_phone,
            potential=counts.potential,
            duplicate_phones=len(duplicates),
            **facets,
        )


class GetLeadUseCase:
    """One lead the caller may read."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.leads = BusinessLeadRepository(session)
        self.presenter = LeadPresenter(session)

    async def execute(self, user_id: UUID, lead_id: UUID) -> LeadSchema:
        """Raises NotFoundError for a lead outside the caller's scope."""
        lead = await self.leads.get_for_user(user_id, lead_id)
        if lead is None:
            raise NotFoundError(entity_name="BusinessLead", entity_id=lead_id)
        duplicates = await self.leads.duplicate_phones(user_id)
        return (
            await self.presenter.present(user_id, [lead], duplicate_phones=duplicates)
        )[0]


class RefreshLeadUseCase:
    """Re-read a lead's details from Google (Place Details)."""

    def __init__(
        self,
        session: MongoSession,
        gateway_factory: GatewayFactory = default_gateway_factory,
    ) -> None:
        """Inject the session and the gateway factory."""
        self.leads = BusinessLeadRepository(session)
        self.presenter = LeadPresenter(session)
        self.gateway_factory = gateway_factory

    async def execute(self, user_id: UUID, lead_id: UUID) -> LeadSchema:
        """Replace the lead's Google content with a fresh read.

        Raises:
            NotFoundError: Not the caller's lead, or Google no longer has it
            ExternalServiceError: No key, or Google refused
        """
        lead = await self.leads.get_for_user(user_id, lead_id)
        if lead is None:
            raise NotFoundError(entity_name="BusinessLead", entity_id=lead_id)
        record = await self.gateway_factory().place_details(lead.place_id)
        if record is None:
            raise NotFoundError(entity_name="Google place", entity_id=lead.place_id)
        now = utc_now()
        lead = await self.leads.refresh_one(
            lead,
            record,
            fetched_at=now,
            expires_at=now + timedelta(days=settings.lead_content_ttl_days),
        )
        duplicates = await self.leads.duplicate_phones(user_id)
        return (
            await self.presenter.present(user_id, [lead], duplicate_phones=duplicates)
        )[0]


class OverviewUseCase:
    """The Lead Finder dashboard."""

    def __init__(
        self,
        session: MongoSession,
        gateway_factory: GatewayFactory = default_gateway_factory,
    ) -> None:
        """Inject the session and the gateway factory."""
        self.leads = BusinessLeadRepository(session)
        self.searches = BusinessSearchRepository(session)
        self.saved = SavedLeadRepository(session)
        self.exports = LeadExportRepository(session)
        self.quota = QuotaService(session)
        self.presenter = LeadPresenter(session)
        self.gateway_factory = gateway_factory

    async def execute(self, user_id: UUID) -> OverviewSchema:
        """Headline counts, today's quota, recent searches and leads."""
        counts = await self.leads.counts(user_id)
        by_status = await self.saved.status_counts(user_id)
        recent_leads = await self.leads.recent_for_user(user_id, limit=8)
        return OverviewSchema(
            stats=OverviewStatsSchema(
                total_businesses=counts.total,
                without_website=counts.without_website,
                with_phone=counts.with_phone,
                potential_leads=counts.potential,
                saved_leads=sum(by_status.values()),
                total_searches=await self.searches.count_for_user(user_id),
                exports=await self.exports.count_for_user(user_id),
            ),
            saved_by_status=by_status,
            quota=await self.quota.quota(user_id),
            recent_searches=search_schemas(
                await self.searches.recent_for_user(user_id, limit=5)
            ),
            recent_leads=await self.presenter.present(user_id, recent_leads),
            places_configured=self.gateway_factory().is_configured,
        )
