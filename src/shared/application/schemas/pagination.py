"""Pagination, search and sort contracts shared by every admin list endpoint.

One definition rather than one per module — ported from hgs-backend, where it
replaced per-module ad-hoc ``{items, total}`` shapes. Every NextHire AI list,
admin and public alike, uses it, so the frontend's table and pager are written
once.

Two pieces:

- ``ListQueryParams`` — what a route accepts, supplied through the
  ``list_query_params`` dependency so the query-string names (``page``,
  ``page_size``, ``search``, ``sort``, ``order``) are identical everywhere.
- ``PaginatedResponseSchema`` — what a route returns: ``{items, total}`` plus
  what a pager needs.

``total`` is the count BEFORE limit/offset. It is what tells the pager how many
pages exist, so counting the returned slice would make every last page claim to
be the only one.
"""

from typing import Generic, List, Literal, Optional, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

TItem = TypeVar("TItem")

#: Hard ceiling on ``page_size``. A caller asking for 10 000 rows gets 100.
#: The dashboard never needs more, and an unbounded limit is how one request
#: serializes an entire table into memory.
MAX_PAGE_SIZE = 100

#: Rows per page when the caller does not say.
DEFAULT_PAGE_SIZE = 20

SortOrder = Literal["asc", "desc"]


class ListQueryParams(BaseModel):
    """Query parameters every admin list endpoint accepts.

    ``page`` is 1-based because it is user-facing — the pager renders it
    directly. ``offset`` does the 0-based conversion once, so no call site has
    to remember the ``- 1``.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    page: int = Field(default=1, ge=1, description="1-based page number")
    page_size: int = Field(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description=f"Rows per page (max {MAX_PAGE_SIZE})",
    )
    search: Optional[str] = Field(
        default=None,
        description="Case-insensitive substring match over the resource's "
        "searchable text columns",
    )
    sort: Optional[str] = Field(
        default=None,
        description="Column to sort by. Repositories check this against an "
        "allowlist, so an unknown name falls back to the default order rather "
        "than reaching the database.",
    )
    order: SortOrder = Field(default="asc", description="Sort direction")

    @property
    def offset(self) -> int:
        """Row offset for the SQL OFFSET clause."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Row count for the SQL LIMIT clause."""
        return self.page_size

    @property
    def normalized_search(self) -> Optional[str]:
        """The search term, or None when it is blank.

        An empty string from a cleared search box means "no filter", not "match
        rows containing nothing" — which, as a ``LIKE '%%'``, matches everything
        and still costs the scan.
        """
        if self.search is None:
            return None
        term = self.search.strip()
        return term or None


def list_query_params(
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description=f"Rows per page (max {MAX_PAGE_SIZE})",
    ),
    search: Optional[str] = Query(default=None, description="Free-text search"),
    sort: Optional[str] = Query(default=None, description="Column to sort by"),
    order: SortOrder = Query(default="asc", description="Sort direction"),
) -> ListQueryParams:
    """FastAPI dependency producing validated list parameters.

    A function rather than ``Depends(ListQueryParams)``: FastAPI renders a
    Pydantic model dependency as one opaque object in the OpenAPI page, which
    loses every per-parameter description above.

    Args:
        page: 1-based page number
        page_size: Rows per page
        search: Free-text search term
        sort: Column name to sort by
        order: Sort direction

    Returns:
        The validated parameters
    """
    return ListQueryParams(
        page=page, page_size=page_size, search=search, sort=sort, order=order
    )


class PaginatedResponseSchema(BaseModel, Generic[TItem]):
    """A page of results plus the metadata a pager needs."""

    items: List[TItem] = Field(default_factory=list, description="The rows")
    total: int = Field(default=0, description="Matching rows BEFORE pagination")
    page: int = Field(default=1, description="1-based page number returned")
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, description="Rows per page")
    total_pages: int = Field(default=0, description="Pages available")

    @classmethod
    def build(
        cls,
        items: List[TItem],
        total: int,
        params: ListQueryParams,
    ) -> "PaginatedResponseSchema[TItem]":
        """Assemble a page response from a slice and its unpaginated count.

        Args:
            items: The rows for this page
            total: Matching rows before limit/offset
            params: The parameters the slice was read with

        Returns:
            The populated response
        """
        page_size = params.page_size
        # Ceiling division without importing math. Zero rows means zero pages,
        # not "page 1 of 1" — an empty list has nothing to page through.
        total_pages = (total + page_size - 1) // page_size if total else 0
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=page_size,
            total_pages=total_pages,
        )


class DeleteResponseSchema(BaseModel):
    """Confirmation that a resource was removed.

    Every delete in this service is a SOFT delete: the row is flagged inactive
    and survives. ``message`` is written for the dashboard's toast, which is why
    it says "removed" rather than promising a permanence the system does not
    deliver.
    """

    id: str = Field(description="ID of the removed resource")
    deleted: bool = Field(default=True)
    message: str = Field(default="Removed")


class ReorderItemSchema(BaseModel):
    """One row's new position in a reorder request."""

    id: str = Field(description="Resource ID")
    display_order: int = Field(ge=0, description="New 0-based sort position")


class ReorderRequestSchema(BaseModel):
    """Payload for the shared reorder endpoint.

    The WHOLE ordered set is sent, not the single row that moved. The dashboard
    already holds every row, and sending all of them makes the write idempotent:
    a replayed request produces the same order instead of shifting everything
    one place further each time.
    """

    items: List[ReorderItemSchema] = Field(
        min_length=1, description="Every row, in its new order"
    )


class ReorderResponseSchema(BaseModel):
    """Confirmation that an ordering was applied."""

    updated: int = Field(default=0, description="Rows whose position changed")
    message: str = Field(default="Order updated")
