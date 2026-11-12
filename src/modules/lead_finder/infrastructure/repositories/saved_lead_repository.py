"""
Saved lead and lead note repository.

Every method takes the caller's ``user_id`` and filters on it: a saved lead or
note of someone else's is never returned, so its id is a 404.
"""

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Type
from uuid import UUID

from pymongo import ASCENDING, DESCENDING

from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.repository_error import RepositoryError
from src.shared.infrastructure.base_repository import BaseRepository
from src.shared.infrastructure.database import MongoSession
from src.shared.infrastructure.ordering import contains_ci

from ...domain.entities.business_lead import BusinessLead
from ...domain.entities.lead_note import LeadNote
from ...domain.entities.saved_lead import SavedLead
from ...domain.enums import LeadStatus

#: Sort keys for the saved list: which side of the pair each one reads.
_SAVED_SORTS = {"created_at", "updated_at", "status"}
_LEAD_SORTS = {"name", "district"}


class SavedLeadRepository(BaseRepository[SavedLead]):
    """Repository for SavedLead and LeadNote database operations."""

    def __init__(self, session: MongoSession, model: Type[SavedLead] = SavedLead):
        """Initialize the saved lead repository."""
        super().__init__(session, model)

    @property
    def _notes(self):  # type: ignore[no-untyped-def]
        return self.session.collection(LeadNote)

    async def get_for_user(self, user_id: UUID, saved_id: UUID) -> Optional[SavedLead]:
        """The caller's saved lead by its own id."""
        try:
            return self.load(
                self.collection.find_one({"_id": saved_id, "user_id": user_id})
            )
        except Exception as e:
            raise RepositoryError(
                entity_name="SavedLead", operation="get_for_user", message=str(e)
            ) from e

    async def by_lead_ids(
        self, user_id: UUID, lead_ids: Iterable[UUID]
    ) -> Dict[UUID, SavedLead]:
        """The caller's saved documents for these leads, keyed by lead id."""
        ids = list(set(lead_ids))
        if not ids:
            return {}
        try:
            rows = self.load_many(
                self.collection.find({"user_id": user_id, "lead_id": {"$in": ids}})
            )
            return {row.lead_id: row for row in rows}
        except Exception as e:
            raise RepositoryError(
                entity_name="SavedLead", operation="by_lead_ids", message=str(e)
            ) from e

    async def list_for_user(
        self,
        user_id: UUID,
        params: ListQueryParams,
        status: Optional[LeadStatus] = None,
    ) -> Tuple[List[Tuple[SavedLead, BusinessLead]], int]:
        """The caller's saved leads with their business, newest first by default.

        Searchable over business name, address, phone and district; sortable
        by ``created_at``, ``updated_at``, ``status``, ``name``, ``district``
        (nulls last either way).

        The pair is joined in Python: the set is bounded by one user's saved
        leads, and a sort on a business field needs both sides anyway.
        """
        try:
            query: dict[str, Any] = {"user_id": user_id}
            if status is not None:
                query["status"] = status.value
            saved = self.load_many(self.collection.find(query))
            if not saved:
                return [], 0

            lead_query: dict[str, Any] = {
                "_id": {"$in": list({row.lead_id for row in saved})}
            }
            term = params.normalized_search
            if term:
                lead_query["$or"] = [
                    {field: contains_ci(term)}
                    for field in (
                        "name",
                        "formatted_address",
                        "phone_display",
                        "district",
                    )
                ]
            leads = {
                lead.id: lead
                for lead in self.session.load_many(
                    BusinessLead, self.session.collection(BusinessLead).find(lead_query)
                )
            }
            pairs = [(row, leads[row.lead_id]) for row in saved if row.lead_id in leads]

            sort = params.sort if params.sort in _SAVED_SORTS | _LEAD_SORTS else None
            field = sort or "created_at"
            descending = params.order == "desc" or params.sort is None

            def value(pair: Tuple[SavedLead, BusinessLead]) -> Any:
                source: Any = pair[1] if field in _LEAD_SORTS else pair[0]
                raw = getattr(source, field)
                return raw.value if isinstance(raw, LeadStatus) else raw

            pairs.sort(key=lambda p: str(p[0].id))
            present = [p for p in pairs if value(p) is not None]
            missing = [p for p in pairs if value(p) is None]
            present.sort(key=value, reverse=descending)
            ordered = present + missing

            page = ordered[params.offset : params.offset + params.limit]
            return page, len(ordered)
        except Exception as e:
            raise RepositoryError(
                entity_name="SavedLead", operation="list_for_user", message=str(e)
            ) from e

    async def status_counts(self, user_id: UUID) -> Dict[LeadStatus, int]:
        """How many of the caller's saved leads sit at each status."""
        try:
            rows = self.collection.aggregate(
                [
                    {"$match": {"user_id": user_id}},
                    {"$group": {"_id": "$status", "count": {"$sum": 1}}},
                ]
            )
            counts = {status: 0 for status in LeadStatus}
            for row in rows:
                counts[LeadStatus(row["_id"])] = int(row["count"])
            return counts
        except Exception as e:
            raise RepositoryError(
                entity_name="SavedLead", operation="status_counts", message=str(e)
            ) from e

    async def saved_lead_ids(
        self, user_id: UUID, lead_ids: Iterable[UUID]
    ) -> Set[UUID]:
        """Which of these leads the caller has saved."""
        return set((await self.by_lead_ids(user_id, lead_ids)).keys())

    async def delete_for_user(self, user_id: UUID, saved_id: UUID) -> bool:
        """Unsave (and drop the notes with it). Returns whether one existed."""
        try:
            result = self.collection.delete_one({"_id": saved_id, "user_id": user_id})
            if result.deleted_count:
                self._notes.delete_many({"saved_lead_id": saved_id, "user_id": user_id})
            return bool(result.deleted_count)
        except Exception as e:
            raise RepositoryError(
                entity_name="SavedLead", operation="delete_for_user", message=str(e)
            ) from e

    # ------------------------------------------------------------------ notes

    async def notes_for(
        self, user_id: UUID, saved_ids: Iterable[UUID]
    ) -> Dict[UUID, List[LeadNote]]:
        """The caller's notes on these saved leads, newest first, keyed by saved id."""
        ids = list(set(saved_ids))
        if not ids:
            return {}
        try:
            cursor = self._notes.find(
                {"user_id": user_id, "saved_lead_id": {"$in": ids}}
            ).sort([("created_at", DESCENDING), ("_id", ASCENDING)])
            grouped: Dict[UUID, List[LeadNote]] = {saved_id: [] for saved_id in ids}
            for note in self.session.load_many(LeadNote, cursor):
                grouped[note.saved_lead_id].append(note)
            return grouped
        except Exception as e:
            raise RepositoryError(
                entity_name="LeadNote", operation="notes_for", message=str(e)
            ) from e

    async def add_note(self, note: LeadNote) -> LeadNote:
        """Persist a note."""
        try:
            self.session.add(note)
            self.session.commit()
            return note
        except Exception as e:
            self.session.rollback()
            raise RepositoryError(
                entity_name="LeadNote", operation="add_note", message=str(e)
            ) from e

    async def delete_note(self, user_id: UUID, saved_id: UUID, note_id: UUID) -> bool:
        """Delete one of the caller's notes. Returns whether it existed."""
        try:
            result = self._notes.delete_one(
                {"_id": note_id, "saved_lead_id": saved_id, "user_id": user_id}
            )
            return bool(result.deleted_count)
        except Exception as e:
            raise RepositoryError(
                entity_name="LeadNote", operation="delete_note", message=str(e)
            ) from e
