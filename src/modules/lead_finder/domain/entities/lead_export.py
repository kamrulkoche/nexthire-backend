"""
LeadExport entity — a record that a lead finder exported leads.
"""

from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from src.shared.domain.entities.base_entity import BaseEntity

from ..enums import ExportFormat


class LeadExport(BaseEntity):
    """
    Export history: when, what format, which filters, how many rows.

    Only the METADATA is stored. The file is generated on request and streamed
    to the user; keeping a copy would be a second, unexpiring store of Google
    content.

    Collection: lead_exports
    """

    __collection__ = "lead_exports"
    __indexes__ = [
        IndexModel(
            [("user_id", ASCENDING), ("created_at", DESCENDING)],
            name="ix_lead_exports_user_created",
        ),
        IndexModel([("search_id", ASCENDING)], name="ix_lead_exports_search_id"),
    ]

    user_id: UUID

    format: ExportFormat

    #: ``search`` (one search's results), ``leads`` (all the user's leads),
    #: ``saved`` (saved leads) or ``selection`` (hand-picked rows).
    scope: str = Field(max_length=20)

    #: Nulled when that search is deleted.
    search_id: Optional[UUID] = Field(default=None)

    row_count: int = Field(default=0)

    file_name: str = Field(max_length=200)

    #: The filters the export was produced with, for the history screen.
    filters: Dict[str, Any] = Field(default_factory=dict)
