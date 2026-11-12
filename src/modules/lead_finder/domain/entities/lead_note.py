"""
LeadNote entity — a note a lead finder wrote on a saved lead.
"""

from uuid import UUID

from pydantic import Field
from pymongo import ASCENDING, IndexModel

from src.shared.domain.entities.base_entity import BaseEntity


class LeadNote(BaseEntity):
    """
    A dated note on a saved lead ("Called, ask for the manager on Sunday").

    A list rather than one text field so the history of contact attempts is
    kept. Owned through the saved lead, and deleted with it; ``user_id`` is
    repeated so every query can filter on the caller directly.

    Collection: lead_notes
    """

    __collection__ = "lead_notes"
    __indexes__ = [
        IndexModel(
            [("saved_lead_id", ASCENDING), ("created_at", ASCENDING)],
            name="ix_lead_notes_saved_lead_created",
        ),
        IndexModel([("user_id", ASCENDING)], name="ix_lead_notes_user_id"),
    ]

    saved_lead_id: UUID

    user_id: UUID

    body: str = Field(max_length=2000)
