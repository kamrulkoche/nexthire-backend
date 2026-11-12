"""Saved leads: save (one or many), list, status pipeline, notes, unsave.

Every method takes the caller's id from the session, never from the request.
"""

from typing import List, Optional, Tuple
from uuid import UUID

from pymongo.errors import DuplicateKeyError
from src.shared.infrastructure.database import MongoSession

from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.not_found_error import NotFoundError
from src.shared.domain.time import utc_now

from ...domain.entities.lead_note import LeadNote
from ...domain.entities.saved_lead import SavedLead
from ...domain.enums import LeadStatus
from ...infrastructure.repositories.business_lead_repository import (
    BusinessLeadRepository,
)
from ...infrastructure.repositories.business_search_repository import (
    BusinessSearchRepository,
)
from ...infrastructure.repositories.saved_lead_repository import SavedLeadRepository
from ..schemas.lead_finder_schema import (
    LeadNoteCreateSchema,
    LeadNoteSchema,
    SavedLeadSchema,
    SaveLeadsResultSchema,
    SaveLeadsSchema,
)
from ..services.lead_presenter import lead_schema


class _SavedUseCase:
    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.session = session
        self.saved = SavedLeadRepository(session)
        self.leads = BusinessLeadRepository(session)
        self.searches = BusinessSearchRepository(session)

    async def _present(
        self, user_id: UUID, rows: List[Tuple[SavedLead, object]]
    ) -> List[SavedLeadSchema]:
        notes = await self.saved.notes_for(
            user_id, (row[0].id for row in rows if row[0].id)
        )
        duplicates = await self.leads.duplicate_phones(user_id)
        result = []
        for saved, lead in rows:
            assert saved.id is not None
            phone = getattr(lead, "phone_normalized", None)
            result.append(
                SavedLeadSchema(
                    id=saved.id,
                    status=saved.status,
                    search_id=saved.search_id,
                    created_at=saved.created_at,
                    updated_at=saved.updated_at,
                    lead=lead_schema(
                        lead,  # type: ignore[arg-type]
                        is_duplicate_phone=bool(phone and phone in duplicates),
                        saved_lead_id=saved.id,
                        saved_status=saved.status,
                    ),
                    notes=[
                        LeadNoteSchema.model_validate(note)
                        for note in notes.get(saved.id, [])
                    ],
                )
            )
        return result

    async def _load(self, user_id: UUID, saved_id: UUID) -> SavedLeadSchema:
        saved = await self.saved.get_for_user(user_id, saved_id)
        if saved is None:
            raise NotFoundError(entity_name="SavedLead", entity_id=saved_id)
        lead = await self.leads.get_by_id(saved.lead_id)
        if lead is None:  # pragma: no cover - FK cascade removes the save first
            raise NotFoundError(entity_name="SavedLead", entity_id=saved_id)
        return (await self._present(user_id, [(saved, lead)]))[0]


class SaveLeadsUseCase(_SavedUseCase):
    """Save one or many leads, skipping ones already saved."""

    async def execute(
        self, user_id: UUID, payload: SaveLeadsSchema
    ) -> SaveLeadsResultSchema:
        """Save every lead the caller may read; never duplicates a save.

        A lead outside the caller's scope is counted as ``not_found`` rather
        than failing the whole batch, so a stale selection still saves the rest.
        """
        search_id: Optional[UUID] = payload.search_id
        if (
            search_id is not None
            and await self.searches.get_for_user(user_id, search_id) is None
        ):
            search_id = None
        requested = list(dict.fromkeys(payload.lead_ids))
        visible = await self.leads.visible_ids(user_id, requested)
        existing = await self.saved.saved_lead_ids(user_id, visible)
        saved = 0
        for lead_id in requested:
            if lead_id not in visible or lead_id in existing:
                continue
            self.session.add(
                SavedLead(
                    user_id=user_id,
                    lead_id=lead_id,
                    status=payload.status,
                    search_id=search_id,
                    created_by=user_id,
                )
            )
            saved += 1
        try:
            self.session.commit()
        except DuplicateKeyError:
            # A double-click raced us; fall back to one at a time.
            self.session.rollback()
            saved = 0
            for lead_id in requested:
                if lead_id not in visible:
                    continue
                if await self.saved.saved_lead_ids(user_id, [lead_id]):
                    continue
                try:
                    await self.saved.create(
                        SavedLead(
                            user_id=user_id,
                            lead_id=lead_id,
                            status=payload.status,
                            search_id=search_id,
                        )
                    )
                    saved += 1
                except DuplicateKeyError:
                    continue
        return SaveLeadsResultSchema(
            saved=saved,
            already_saved=len([lead for lead in requested if lead in existing]),
            not_found=len([lead for lead in requested if lead not in visible]),
        )


class ListSavedLeadsUseCase(_SavedUseCase):
    """The caller's saved leads."""

    async def execute(
        self, user_id: UUID, params: ListQueryParams, status: Optional[LeadStatus]
    ) -> Tuple[List[SavedLeadSchema], int]:
        """A page of saved leads with notes."""
        rows, total = await self.saved.list_for_user(user_id, params, status)
        return await self._present(user_id, rows), total  # type: ignore[arg-type]


class GetSavedLeadUseCase(_SavedUseCase):
    """One saved lead."""

    async def execute(self, user_id: UUID, saved_id: UUID) -> SavedLeadSchema:
        """Raises NotFoundError if it is not the caller's."""
        return await self._load(user_id, saved_id)


class UpdateSavedLeadUseCase(_SavedUseCase):
    """Move a saved lead along the pipeline."""

    async def execute(
        self, user_id: UUID, saved_id: UUID, status: LeadStatus
    ) -> SavedLeadSchema:
        """Raises NotFoundError if it is not the caller's."""
        saved = await self.saved.get_for_user(user_id, saved_id)
        if saved is None:
            raise NotFoundError(entity_name="SavedLead", entity_id=saved_id)
        saved.status = status
        saved.updated_by = user_id
        await self.saved.update(saved)
        return await self._load(user_id, saved_id)


class UnsaveLeadUseCase(_SavedUseCase):
    """Remove a saved lead and its notes."""

    async def execute(self, user_id: UUID, saved_id: UUID) -> None:
        """Raises NotFoundError if it is not the caller's."""
        if not await self.saved.delete_for_user(user_id, saved_id):
            raise NotFoundError(entity_name="SavedLead", entity_id=saved_id)


class AddLeadNoteUseCase(_SavedUseCase):
    """Write a note on a saved lead."""

    async def execute(
        self, user_id: UUID, saved_id: UUID, payload: LeadNoteCreateSchema
    ) -> SavedLeadSchema:
        """Raises NotFoundError if the saved lead is not the caller's."""
        saved = await self.saved.get_for_user(user_id, saved_id)
        if saved is None:
            raise NotFoundError(entity_name="SavedLead", entity_id=saved_id)
        await self.saved.add_note(
            LeadNote(saved_lead_id=saved_id, user_id=user_id, body=payload.body)
        )
        saved.updated_at = utc_now()
        await self.saved.update(saved)
        return await self._load(user_id, saved_id)


class DeleteLeadNoteUseCase(_SavedUseCase):
    """Delete a note."""

    async def execute(
        self, user_id: UUID, saved_id: UUID, note_id: UUID
    ) -> SavedLeadSchema:
        """Raises NotFoundError if the note is not the caller's."""
        if not await self.saved.delete_note(user_id, saved_id, note_id):
            raise NotFoundError(entity_name="LeadNote", entity_id=note_id)
        return await self._load(user_id, saved_id)
