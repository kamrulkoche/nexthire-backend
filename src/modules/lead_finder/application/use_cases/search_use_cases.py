"""Running a business search.

Two steps, split like a collection run so the slow one happens after the
response:

1. ``StartSearchUseCase`` validates the keyword and locations, checks the
   caller's daily quota and that they have no search already running, and
   records a QUEUED search. Fast; the route does it inline so the screen gets
   the search id (or a 409 / 429) at once.
2. ``ExecuteSearchUseCase`` claims the search (atomic UPDATE), runs one Text
   Search query per target, page by page, stores and de-duplicates the places,
   links them to the search, updates progress as it goes, and finishes with the
   summary counts. Slow; runs on the task dispatcher with its own session.

Cost control: every HTTP attempt counts. A search stops at the smaller of the
per-search cap and what is left of the caller's daily quota, and is marked
PARTIAL with a message saying so.
"""

from datetime import timedelta
from typing import Callable, List, Optional, Tuple
from uuid import UUID

from src.shared.infrastructure.database import MongoSession

from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.not_found_error import NotFoundError
from src.shared.domain.exceptions.quota_exceeded_error import QuotaExceededError
from src.shared.domain.exceptions.validation_error import ValidationError
from src.shared.domain.text import clip
from src.shared.domain.time import utc_now
from src.shared.infrastructure.logging import get_logger
from src.shared.utils.config import settings

from ...domain.entities.business_search import BusinessSearch
from ...domain.enums import SearchStatus
from ...domain.exceptions import SearchInProgressError
from ...domain.services.bangladesh_locations import (
    LocationSelection,
    SearchTarget,
    UnknownLocationError,
    describe_selection,
    resolve_targets,
    selections_from_stored,
    summarize_selection,
)
from ...domain.services.categories import is_known_category
from ...domain.services.places_gateway import PlacesGateway
from ...infrastructure.external.google_places_client import (
    GooglePlacesClient,
    PlacesApiError,
    PlacesNotConfiguredError,
)
from ...infrastructure.repositories.business_lead_repository import (
    BusinessLeadRepository,
)
from ...infrastructure.repositories.business_search_repository import (
    BusinessSearchRepository,
)
from ...infrastructure.repositories.lead_finder_settings_repository import (
    LeadFinderSettingsRepository,
)
from ..schemas.lead_finder_schema import QuotaSchema, SearchSchema, StartSearchSchema
from ..services.lead_presenter import search_schema, search_schemas

logger = get_logger(__name__)

GatewayFactory = Callable[[], PlacesGateway]

#: A search still QUEUED/RUNNING after this long was killed by a restart.
STALE_SEARCH_AFTER = timedelta(hours=2)


def default_gateway_factory() -> PlacesGateway:
    """The real Google client, configured from settings."""
    return GooglePlacesClient()


# -------------------------------------------------------------------- quota


class QuotaService:
    """The caller's daily allowance of Places requests (UTC day)."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.searches = BusinessSearchRepository(session)
        self.settings = LeadFinderSettingsRepository(session)

    async def quota(self, user_id: UUID) -> QuotaSchema:
        """Today's limit, use and reset time for one user."""
        config = await self.settings.get_or_create()
        now = utc_now()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        used = await self.searches.requests_since(day_start, user_id)
        return QuotaSchema(
            limit=config.daily_request_quota,
            used=used,
            remaining=max(0, config.daily_request_quota - used),
            max_per_search=config.max_requests_per_search,
            resets_at=day_start + timedelta(days=1),
        )

    async def budget(self, user_id: UUID) -> Tuple[int, QuotaSchema]:
        """Requests the next search may spend, and the quota it came from."""
        quota = await self.quota(user_id)
        return min(quota.max_per_search, quota.remaining), quota


def _quota_error(quota: QuotaSchema) -> QuotaExceededError:
    retry = max(1, int((quota.resets_at - utc_now()).total_seconds()))
    return QuotaExceededError(
        "places_daily",
        f"You have used today's {quota.limit} Google Places requests. "
        "The allowance resets at midnight UTC.",
        limit=quota.limit,
        used=quota.used,
        retry_after_seconds=retry,
    )


def _selections(payload: StartSearchSchema) -> List[LocationSelection]:
    return [
        LocationSelection(
            division=item.division,
            district=item.district,
            upazila=item.upazila,
            area=item.area,
        )
        for item in payload.locations
    ]


# ------------------------------------------------------------------- start


class StartSearchUseCase:
    """Validate, check limits, and queue a search."""

    def __init__(
        self,
        session: MongoSession,
        gateway_factory: GatewayFactory = default_gateway_factory,
    ) -> None:
        """Inject the session and the Places gateway factory."""
        self.searches = BusinessSearchRepository(session)
        self.quota = QuotaService(session)
        self.gateway_factory = gateway_factory

    async def execute(self, user_id: UUID, payload: StartSearchSchema) -> SearchSchema:
        """Record a QUEUED search. The caller dispatches the execution.

        Raises:
            ValidationError: Unknown location or category
            ExternalServiceError: No Google Maps API key configured
            AlreadyExistsError: The caller already has a search running (409)
            QuotaExceededError: Today's Places requests are spent (429)
        """
        if payload.category and not is_known_category(payload.category):
            raise ValidationError("BusinessSearch", "category", "Unknown category.")

        selections = _selections(payload)
        try:
            targets = resolve_targets(selections)
            described = describe_selection(selections)
        except UnknownLocationError as e:
            raise ValidationError("BusinessSearch", "locations", str(e)) from e

        if not self.gateway_factory().is_configured:
            raise PlacesNotConfiguredError()

        if await self.searches.has_active(user_id):
            raise SearchInProgressError()

        budget, quota = await self.quota.budget(user_id)
        if budget <= 0:
            raise _quota_error(quota)

        search = await self.searches.create(
            BusinessSearch(
                user_id=user_id,
                keyword=payload.keyword,
                category=payload.category,
                locations=described,
                location_label=clip(summarize_selection(described), 300)
                or "All Bangladesh",
                status=SearchStatus.QUEUED,
                total_targets=len(targets),
            )
        )
        logger.info(
            f"Search queued: '{payload.keyword}' over {len(targets)} target(s), "
            f"budget {budget} requests"
        )
        return search_schema(search)


# ----------------------------------------------------------------- execute


class ExecuteSearchUseCase:
    """Do the work of a queued search."""

    def __init__(
        self,
        session: MongoSession,
        gateway_factory: GatewayFactory = default_gateway_factory,
    ) -> None:
        """Inject a session of the worker's own and the gateway factory."""
        self.session = session
        self.searches = BusinessSearchRepository(session)
        self.leads = BusinessLeadRepository(session)
        self.quota = QuotaService(session)
        self.gateway_factory = gateway_factory

    async def execute(self, search_id: UUID) -> Optional[BusinessSearch]:
        """Run the search. Never raises for an API failure: the search is
        recorded as FAILED or PARTIAL with a readable message.

        Returns:
            The finished search, or None if another worker already took it
        """
        search = await self.searches.get_by_id(search_id)
        if search is None:
            raise NotFoundError(entity_name="BusinessSearch", entity_id=search_id)
        if not await self.searches.claim(search_id, utc_now()):
            logger.info(f"Search {search_id} already claimed; skipping")
            return None
        self.session.refresh(search)

        gateway = self.gateway_factory()
        budget, _ = await self.quota.budget(search.user_id)
        targets = resolve_targets(selections_from_stored(search.locations))
        ttl = timedelta(days=settings.lead_content_ttl_days)

        position = 0
        fatal: Optional[str] = None
        stopped_for_budget = False
        target_errors: List[str] = []

        for target in targets:
            if gateway.requests_made >= budget:
                stopped_for_budget = True
                break
            try:
                position = await self._search_target(
                    search, target, gateway, budget, position, ttl
                )
                search.completed_targets += 1
            except PlacesNotConfiguredError as e:
                fatal = e.message
                break
            except PlacesApiError as e:
                if e.status in (401, 403, 429):
                    # The key or the account's quota: every other target would
                    # fail the same way, and retrying them only costs money.
                    fatal = e.message
                    break
                search.failed_targets += 1
                target_errors.append(f"{target.label}: {e.message}")
                logger.warning(f"Search {search_id} target '{target.label}' failed")
            except Exception as e:  # never leave a search stuck in RUNNING
                logger.error(f"Search {search_id} crashed: {e}", exc_info=True)
                fatal = "The search stopped unexpectedly. Try again."
                break
            search.api_requests = gateway.requests_made
            search.total_results = position
            self.session.add(search)
            self.session.commit()

        return await self._finish(
            search, gateway, fatal, stopped_for_budget, target_errors, budget
        )

    async def _search_target(
        self,
        search: BusinessSearch,
        target: SearchTarget,
        gateway: PlacesGateway,
        budget: int,
        position: int,
        ttl: timedelta,
    ) -> int:
        """Every page of one target's query. Returns the new result count."""
        assert search.id is not None
        token: Optional[str] = None
        for _page in range(settings.places_max_pages_per_query):
            if gateway.requests_made >= budget:
                break
            records, token = await gateway.text_search(
                target.query(search.keyword), token
            )
            now = utc_now()
            rows = await self.leads.upsert_places(
                records, target, fetched_at=now, expires_at=now + ttl
            )
            position += await self.leads.link_results(
                search.id, [row.id for row in rows if row.id is not None], position
            )
            if not token:
                break
        return position

    async def _finish(
        self,
        search: BusinessSearch,
        gateway: PlacesGateway,
        fatal: Optional[str],
        stopped_for_budget: bool,
        target_errors: List[str],
        budget: int,
    ) -> BusinessSearch:
        """Snapshot the counts and set the final status and message."""
        assert search.id is not None
        counts = await self.leads.counts(search.user_id, search.id)
        search.total_results = counts.total
        search.leads_found = counts.potential
        search.with_phone = counts.with_phone
        search.without_website = counts.without_website
        search.api_requests = gateway.requests_made
        search.finished_at = utc_now()

        if fatal:
            search.status = (
                SearchStatus.PARTIAL if counts.total else SearchStatus.FAILED
            )
            search.error_message = clip(fatal, 500)
        elif stopped_for_budget:
            search.status = SearchStatus.PARTIAL
            search.error_message = clip(
                f"Stopped after {gateway.requests_made} Google requests (the "
                f"per-search limit or today's remaining quota, {budget}). "
                f"{search.completed_targets} of {search.total_targets} locations "
                "were searched. Narrow the locations to cover the rest.",
                500,
            )
        elif target_errors:
            search.status = (
                SearchStatus.PARTIAL if counts.total else SearchStatus.FAILED
            )
            search.error_message = clip(
                f"{len(target_errors)} location(s) failed. "
                + "; ".join(target_errors[:3]),
                500,
            )
        else:
            search.status = SearchStatus.COMPLETED
            search.error_message = None

        self.session.add(search)
        self.session.commit()
        self.session.refresh(search)
        logger.info(
            f"Search {search.id} {search.status.value}: {counts.total} businesses, "
            f"{counts.potential} potential leads, {gateway.requests_made} requests"
        )
        return search


# ------------------------------------------------------------------- reads


class ListSearchesUseCase:
    """The caller's search history."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.searches = BusinessSearchRepository(session)

    async def execute(
        self, user_id: UUID, params: ListQueryParams, status: Optional[SearchStatus]
    ) -> Tuple[List[SearchSchema], int]:
        """A page of searches."""
        rows, total = await self.searches.list_for_user(user_id, params, status)
        return search_schemas(rows), total


class GetSearchUseCase:
    """One of the caller's searches — polled for progress while it runs."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.searches = BusinessSearchRepository(session)

    async def execute(self, user_id: UUID, search_id: UUID) -> SearchSchema:
        """Raises NotFoundError for an unknown or someone else's search."""
        search = await self.searches.get_for_user(user_id, search_id)
        if search is None:
            raise NotFoundError(entity_name="BusinessSearch", entity_id=search_id)
        return search_schema(search)


class DeleteSearchUseCase:
    """Remove a search from the history (its leads stay if saved)."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.searches = BusinessSearchRepository(session)

    async def execute(self, user_id: UUID, search_id: UUID) -> None:
        """Raises NotFoundError, or AlreadyExistsError (409) while it runs."""
        search = await self.searches.get_for_user(user_id, search_id)
        if search is None:
            raise NotFoundError(entity_name="BusinessSearch", entity_id=search_id)
        if not search.status.is_finished:
            raise SearchInProgressError()
        await self.searches.delete_for_user(user_id, search_id)


class RerunSearchUseCase:
    """Start a new search with an old one's keyword and locations."""

    def __init__(
        self,
        session: MongoSession,
        gateway_factory: GatewayFactory = default_gateway_factory,
    ) -> None:
        """Inject the session and the gateway factory."""
        self.searches = BusinessSearchRepository(session)
        self.start = StartSearchUseCase(session, gateway_factory)

    async def execute(self, user_id: UUID, search_id: UUID) -> SearchSchema:
        """Queue the copy. Same errors as ``StartSearchUseCase``."""
        search = await self.searches.get_for_user(user_id, search_id)
        if search is None:
            raise NotFoundError(entity_name="BusinessSearch", entity_id=search_id)
        selections = selections_from_stored(search.locations)
        payload = StartSearchSchema(
            keyword=search.keyword,
            category=search.category,
            locations=[
                {
                    "division": s.division,
                    "district": s.district,
                    "upazila": s.upazila,
                    "area": s.area,
                }
                for s in selections
            ],
        )
        return await self.start.execute(user_id, payload)


class SearchMaintenanceUseCase:
    """The scheduler's housekeeping: expired content and stuck searches."""

    def __init__(self, session: MongoSession) -> None:
        """Inject a session of the scheduler's own."""
        self.searches = BusinessSearchRepository(session)
        self.leads = BusinessLeadRepository(session)

    async def execute(self) -> Tuple[int, int]:
        """Purge expired Google content; fail searches a restart orphaned.

        Returns:
            ``(leads purged, searches failed)``
        """
        now = utc_now()
        purged = await self.leads.purge_expired_content(now)
        failed = await self.searches.fail_stale(now - STALE_SEARCH_AFTER, now)
        if purged or failed:
            logger.info(
                f"Lead maintenance: purged {purged} lead(s), failed {failed} search(es)"
            )
        return purged, failed
