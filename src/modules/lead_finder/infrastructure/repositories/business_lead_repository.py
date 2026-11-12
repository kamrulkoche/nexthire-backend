"""
Business lead repository.

A lead has no owner: two users can find the same hospital. What a user may
read is decided here, in ONE place — ``_scope_ids``: the leads one of THEIR
searches found, or that they saved. Every read takes the caller's ``user_id``
and goes through it, so another user's search id simply matches nothing.

MongoDB has no joins, so the scope is resolved to a set of lead ids first
(results of the caller's searches, plus their saved leads) and every query
filters on ``_id: {$in: ...}``. Ordering the SQL version did with CASE /
NULLS LAST / a join on the result position is done in Python over the
filtered set, which one user's leads keep small.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Type
from uuid import UUID, uuid4

from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection

from src.shared.domain.exceptions.repository_error import RepositoryError
from src.shared.domain.time import utc_now
from src.shared.infrastructure.base_repository import BaseRepository
from src.shared.infrastructure.database import MongoSession
from src.shared.infrastructure.ordering import contains_ci

from ...domain.entities.business_lead import GOOGLE_CONTENT_FIELDS, BusinessLead
from ...domain.entities.business_search import BusinessSearch
from ...domain.entities.saved_lead import SavedLead
from ...domain.entities.search_result import BusinessSearchResult
from ...domain.services.bangladesh_locations import SearchTarget
from ...domain.services.phone import normalize_phone
from ...domain.value_objects.lead_filter import LeadFilter
from ...domain.value_objects.place_record import PlaceRecord


@dataclass(frozen=True)
class LeadCounts:
    """The four numbers the dashboard and a search's summary show."""

    total: int
    without_website: int
    with_phone: int
    potential: int


#: No website AND a phone number — the default lead rule, as a filter.
POTENTIAL_FILTER: Dict[str, Any] = {"has_phone": True, "has_website": False}

#: Sort keys that order by one lead field, nulls last either way.
_FIELD_SORTS = {"name", "rating", "review_count", "district"}


class BusinessLeadRepository(BaseRepository[BusinessLead]):
    """Repository for BusinessLead database operations."""

    def __init__(self, session: MongoSession, model: Type[BusinessLead] = BusinessLead):
        """Initialize the business lead repository."""
        super().__init__(session, model)

    @property
    def _results(self) -> Collection:
        return self.session.collection(BusinessSearchResult)

    # ------------------------------------------------------------------ writes

    async def upsert_places(
        self,
        records: List[PlaceRecord],
        target: Optional[SearchTarget],
        *,
        fetched_at: datetime,
        expires_at: datetime,
    ) -> List[BusinessLead]:
        """Insert new places and refresh known ones, de-duplicated by place ID.

        A place already stored keeps its document (and so every search and
        saved lead pointing at it); its Google content is replaced with what
        was just fetched and its expiry pushed forward. The location the
        search attributed it to is only filled where empty, so the first
        search that found a business decides its district.

        Returns:
            The leads, in the order of ``records`` (duplicates collapsed)
        """
        unique: Dict[str, PlaceRecord] = {}
        for record in records:
            unique.setdefault(record.place_id, record)
        if not unique:
            return []
        try:
            existing = {
                lead.place_id: lead
                for lead in self.load_many(
                    self.collection.find({"place_id": {"$in": list(unique)}})
                )
            }
            rows: List[BusinessLead] = []
            for place_id, record in unique.items():
                lead = existing.get(place_id) or BusinessLead(place_id=place_id)
                apply_place(lead, record, fetched_at=fetched_at, expires_at=expires_at)
                if target is not None:
                    lead.division = lead.division or target.division
                    lead.district = lead.district or target.district
                    lead.upazila = lead.upazila or target.upazila
                    lead.area = lead.area or target.area
                lead.updated_at = fetched_at
                self.session.add(lead)
                rows.append(lead)
            self.session.commit()
            return rows
        except Exception as e:
            self.session.rollback()
            raise RepositoryError(
                entity_name="BusinessLead", operation="upsert_places", message=str(e)
            ) from e

    async def link_results(
        self, search_id: UUID, lead_ids: List[UUID], start_position: int
    ) -> int:
        """Attach leads to a search, skipping ones already attached.

        Returns:
            How many new results were added
        """
        if not lead_ids:
            return 0
        try:
            present = set(
                self._results.distinct(
                    "lead_id", {"search_id": search_id, "lead_id": {"$in": lead_ids}}
                )
            )
            fresh = [
                lead_id for lead_id in dict.fromkeys(lead_ids) if lead_id not in present
            ]
            if fresh:
                now = utc_now()
                self._results.insert_many(
                    [
                        {
                            "_id": uuid4(),
                            "search_id": search_id,
                            "lead_id": lead_id,
                            "position": start_position + offset,
                            "created_at": now,
                        }
                        for offset, lead_id in enumerate(fresh)
                    ]
                )
            return len(fresh)
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessSearchResult",
                operation="link_results",
                message=str(e),
            ) from e

    async def refresh_one(
        self,
        lead: BusinessLead,
        record: PlaceRecord,
        *,
        fetched_at: datetime,
        expires_at: datetime,
    ) -> BusinessLead:
        """Replace one lead's Google content with a fresh Place Details read."""
        apply_place(lead, record, fetched_at=fetched_at, expires_at=expires_at)
        return await self.update(lead)

    async def purge_expired_content(self, now: datetime) -> int:
        """Wipe Google content whose retention window has passed.

        Keeps the document, its place ID and the location the search
        attributed it to, so saved leads, notes and search history survive;
        "Refresh" re-reads the content.

        Returns:
            How many leads were purged
        """
        try:
            values: Dict[str, Any] = {name: None for name in GOOGLE_CONTENT_FIELDS}
            values.update(
                has_website=False,
                has_phone=False,
                content_purged=True,
                content_expires_at=None,
                updated_at=now,
            )
            result = self.collection.update_many(
                {
                    "content_purged": False,
                    "content_expires_at": {"$ne": None, "$lt": now},
                },
                {"$set": values},
            )
            return int(result.modified_count)
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessLead",
                operation="purge_expired_content",
                message=str(e),
            ) from e

    # ------------------------------------------------------------------- reads

    def _search_ids(self, user_id: UUID) -> List[UUID]:
        return list(
            self.session.collection(BusinessSearch).distinct(
                "_id", {"user_id": user_id}
            )
        )

    def _saved_ids(self, user_id: UUID) -> Set[UUID]:
        return set(
            self.session.collection(SavedLead).distinct("lead_id", {"user_id": user_id})
        )

    def _scope_ids(self, user_id: UUID, search_id: Optional[UUID] = None) -> Set[UUID]:
        """The ids of the leads this user may read.

        With a ``search_id``: the results of that search, if it is theirs.
        Without: anything any of their searches found, or that they saved.
        """
        searches = self._search_ids(user_id)
        if search_id is not None:
            if search_id not in searches:
                return set()
            return set(self._results.distinct("lead_id", {"search_id": search_id}))
        found: Set[UUID] = (
            set(self._results.distinct("lead_id", {"search_id": {"$in": searches}}))
            if searches
            else set()
        )
        return found | self._saved_ids(user_id)

    def _scope(self, user_id: UUID, search_id: Optional[UUID] = None) -> Dict[str, Any]:
        """The filter "this user may read this lead"."""
        return {"_id": {"$in": list(self._scope_ids(user_id, search_id))}}

    def _duplicate_phone_set(
        self, user_id: UUID, search_id: Optional[UUID]
    ) -> Set[str]:
        """Normalized numbers that more than one lead in scope shares."""
        rows = self.collection.aggregate(
            [
                {
                    "$match": {
                        **self._scope(user_id, search_id),
                        "phone_normalized": {"$ne": None},
                    }
                },
                {"$group": {"_id": "$phone_normalized", "n": {"$sum": 1}}},
                {"$match": {"n": {"$gt": 1}}},
            ]
        )
        return {row["_id"] for row in rows if row["_id"]}

    def _query(self, user_id: UUID, filters: LeadFilter) -> Dict[str, Any]:
        """Every condition the filter asks for, scope first, ANDed."""
        ids = self._scope_ids(user_id, filters.search_id)
        if filters.lead_ids:
            ids &= set(filters.lead_ids)
        if filters.saved is not None:
            saved = self._saved_ids(user_id)
            ids = ids & saved if filters.saved else ids - saved
        conditions: List[Dict[str, Any]] = [{"_id": {"$in": list(ids)}}]

        if filters.website == "with":
            conditions.append({"has_website": True})
        elif filters.website == "without":
            conditions.append({"has_website": False})
        if filters.phone == "with":
            conditions.append({"has_phone": True})
        elif filters.phone == "without":
            conditions.append({"has_phone": False})
        if filters.min_rating is not None:
            conditions.append({"rating": {"$gte": filters.min_rating}})
        if filters.min_reviews is not None:
            conditions.append({"review_count": {"$gte": filters.min_reviews}})
        if filters.division:
            conditions.append({"division": filters.division})
        if filters.district:
            conditions.append({"district": filters.district})
        if filters.category:
            conditions.append(
                {
                    "$or": [
                        {"primary_category": contains_ci(filters.category)},
                        {"primary_type": contains_ci(filters.category)},
                    ]
                }
            )
        if filters.text:
            digits = "".join(ch for ch in filters.text if ch.isdigit())
            text_conditions: List[Dict[str, Any]] = [
                {"name": contains_ci(filters.text)},
                {"formatted_address": contains_ci(filters.text)},
                {"phone_display": contains_ci(filters.text)},
            ]
            if len(digits) >= 4:
                text_conditions.append({"phone_normalized": contains_ci(digits)})
            conditions.append({"$or": text_conditions})
        if filters.duplicate_phone_only:
            phones = self._duplicate_phone_set(user_id, filters.search_id)
            conditions.append({"phone_normalized": {"$in": list(phones)}})
        return conditions[0] if len(conditions) == 1 else {"$and": conditions}

    def _ordered(
        self,
        leads: List[BusinessLead],
        filters: LeadFilter,
        sort: Optional[str],
        order: str,
    ) -> List[BusinessLead]:
        """Apply the requested order, potential leads first by default.

        Python sorts are stable, so the tiebreakers are applied first and the
        primary key last.
        """
        if sort is not None and sort in _FIELD_SORTS:
            field = sort
            leads.sort(key=lambda lead: str(lead.id))
            leads.sort(key=lambda lead: (lead.name is None, lead.name or ""))
            present = [lead for lead in leads if getattr(lead, field) is not None]
            missing = [lead for lead in leads if getattr(lead, field) is None]
            present.sort(key=lambda lead: getattr(lead, field), reverse=order == "desc")
            return present + missing

        def potential_rank(lead: BusinessLead) -> int:
            return 0 if lead.is_potential_lead else 1

        if filters.search_id is not None:
            positions: Dict[UUID, int] = {
                row["lead_id"]: row["position"]
                for row in self._results.find(
                    {
                        "search_id": filters.search_id,
                        "lead_id": {"$in": [lead.id for lead in leads]},
                    },
                    {"lead_id": 1, "position": 1},
                )
            }
            return sorted(
                leads,
                key=lambda lead: (
                    potential_rank(lead),
                    positions.get(lead.id, 0),
                    str(lead.id),
                ),
            )

        leads.sort(key=lambda lead: str(lead.id))
        leads.sort(key=lambda lead: lead.created_at, reverse=True)
        leads.sort(key=potential_rank)
        return leads

    async def list_for_user(
        self,
        user_id: UUID,
        filters: LeadFilter,
        *,
        offset: int,
        limit: Optional[int],
        sort: Optional[str] = None,
        order: str = "asc",
    ) -> Tuple[List[BusinessLead], int]:
        """A page of the caller's leads, filtered and sorted.

        Args:
            limit: None for every lead (an export)

        Returns:
            ``(leads, total before pagination)``
        """
        try:
            leads = self.load_many(self.collection.find(self._query(user_id, filters)))
            ordered = self._ordered(leads, filters, sort, order)
            end = None if limit is None else offset + limit
            return ordered[offset:end], len(ordered)
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessLead", operation="list_for_user", message=str(e)
            ) from e

    async def get_for_user(
        self, user_id: UUID, lead_id: UUID
    ) -> Optional[BusinessLead]:
        """One lead, if the caller may read it."""
        try:
            if lead_id not in self._scope_ids(user_id):
                return None
            return self.load(self.collection.find_one({"_id": lead_id}))
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessLead", operation="get_for_user", message=str(e)
            ) from e

    async def visible_ids(self, user_id: UUID, lead_ids: Iterable[UUID]) -> Set[UUID]:
        """Which of these ids the caller may read."""
        ids = set(lead_ids)
        if not ids:
            return set()
        try:
            candidates = ids & self._scope_ids(user_id)
            if not candidates:
                return set()
            return set(
                self.collection.distinct("_id", {"_id": {"$in": list(candidates)}})
            )
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessLead", operation="visible_ids", message=str(e)
            ) from e

    async def duplicate_phones(
        self, user_id: UUID, search_id: Optional[UUID] = None
    ) -> Set[str]:
        """Normalized numbers shared by more than one lead in scope."""
        try:
            return self._duplicate_phone_set(user_id, search_id)
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessLead", operation="duplicate_phones", message=str(e)
            ) from e

    async def counts(
        self, user_id: UUID, search_id: Optional[UUID] = None
    ) -> LeadCounts:
        """Totals over the caller's leads (or one search's)."""
        try:
            base = {**self._scope(user_id, search_id), "content_purged": False}
            count = self.collection.count_documents
            return LeadCounts(
                total=int(count(base)),
                without_website=int(count({**base, "has_website": False})),
                with_phone=int(count({**base, "has_phone": True})),
                potential=int(count({**base, **POTENTIAL_FILTER})),
            )
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessLead", operation="counts", message=str(e)
            ) from e

    async def facets(
        self, user_id: UUID, search_id: Optional[UUID] = None
    ) -> Dict[str, List[str]]:
        """Distinct districts, divisions and categories in scope, for filter menus."""
        try:
            scope = self._scope(user_id, search_id)

            def distinct_values(field: str) -> List[str]:
                return sorted(v for v in self.collection.distinct(field, scope) if v)

            return {
                "divisions": distinct_values("division"),
                "districts": distinct_values("district"),
                "categories": distinct_values("primary_category")[:100],
            }
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessLead", operation="facets", message=str(e)
            ) from e

    async def recent_for_user(
        self, user_id: UUID, limit: int = 8
    ) -> List[BusinessLead]:
        """The caller's most recently found potential leads."""
        try:
            cursor = (
                self.collection.find({**self._scope(user_id), **POTENTIAL_FILTER})
                .sort([("updated_at", DESCENDING), ("_id", ASCENDING)])
                .limit(limit)
            )
            return self.load_many(cursor)
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessLead", operation="recent_for_user", message=str(e)
            ) from e

    async def count_all(self) -> int:
        """Every lead stored, for the admin overview."""
        try:
            return int(self.collection.count_documents({}))
        except Exception as e:
            raise RepositoryError(
                entity_name="BusinessLead", operation="count_all", message=str(e)
            ) from e


def apply_place(
    lead: BusinessLead,
    record: PlaceRecord,
    *,
    fetched_at: datetime,
    expires_at: datetime,
) -> None:
    """Copy a place's Google content onto a lead and derive its flags.

    The phone flags are derived from what Google returned and nothing else:
    no number from Google, no number here.
    """
    lead.name = record.name
    lead.primary_category = record.primary_category
    lead.primary_type = record.primary_type
    lead.types = list(record.types) or None
    lead.rating = record.rating
    lead.review_count = record.review_count
    lead.formatted_address = record.formatted_address
    lead.phone_display = record.phone_display
    lead.phone_international = record.phone_international
    lead.phone_normalized = normalize_phone(
        record.phone_display, record.phone_international
    )
    lead.website_uri = record.website_uri
    lead.google_maps_uri = record.google_maps_uri
    lead.latitude = record.latitude
    lead.longitude = record.longitude
    lead.opening_hours = list(record.opening_hours) or None
    lead.business_status = record.business_status
    lead.has_website = bool(record.website_uri)
    lead.has_phone = bool(record.phone_display or record.phone_international)
    lead.fetched_at = fetched_at
    lead.content_expires_at = expires_at
    lead.content_purged = False
