"""
BusinessSearchResult entity — which leads a search found.
"""

from uuid import UUID

from pydantic import Field
from pymongo import ASCENDING, IndexModel

from src.shared.domain.entities.base_entity import BaseEntity


class BusinessSearchResult(BaseEntity):
    """
    The link between a search and the leads it found.

    Unique per (search, lead): a hospital found under two of the search's
    districts is one result. ``position`` keeps Google's relevance order for
    the default sort. Deleted with its search.

    This is also how ownership of a lead works: a user can read a lead when
    one of THEIR searches found it, or they saved it. A lead has no owner of
    its own, because two users may find the same business.

    Collection: business_search_results
    """

    __collection__ = "business_search_results"
    __indexes__ = [
        IndexModel(
            [("search_id", ASCENDING), ("lead_id", ASCENDING)],
            unique=True,
            name="uq_search_results_search_lead",
        ),
        IndexModel([("lead_id", ASCENDING)], name="ix_search_results_lead_id"),
    ]

    search_id: UUID

    lead_id: UUID

    position: int = Field(default=0)
