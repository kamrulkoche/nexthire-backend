"""
SavedLead entity — a business a lead finder kept to work on.
"""

from typing import Optional
from uuid import UUID

from pydantic import Field
from pymongo import ASCENDING, IndexModel

from src.shared.domain.entities.audited_entity import AuditedEntity

from ..enums import LeadStatus


class SavedLead(AuditedEntity):
    """
    One lead one user saved, with their pipeline status.

    Unique per (user, lead), so saving twice — or saving a selection that
    includes leads already saved — never makes a duplicate. Unsaving is a real
    delete of the user's own document (its notes go with it).

    Everything here is the USER's data and is kept indefinitely; the business
    details come from the lead document and expire with it.

    Collection: saved_leads
    """

    __collection__ = "saved_leads"
    __indexes__ = [
        IndexModel(
            [("user_id", ASCENDING), ("lead_id", ASCENDING)],
            unique=True,
            name="uq_saved_leads_user_lead",
        ),
        IndexModel(
            [("user_id", ASCENDING), ("status", ASCENDING)],
            name="ix_saved_leads_user_status",
        ),
        IndexModel([("lead_id", ASCENDING)], name="ix_saved_leads_lead_id"),
        IndexModel([("search_id", ASCENDING)], name="ix_saved_leads_search_id"),
    ]

    user_id: UUID

    lead_id: UUID

    status: LeadStatus = Field(default=LeadStatus.NEW)

    #: The search the lead was saved from, for context. Nulled if that search
    #: is deleted.
    search_id: Optional[UUID] = Field(default=None)
