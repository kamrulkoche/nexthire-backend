"""Shared application schemas.

Contracts used by more than one module. A schema only one module returns lives
in that module's own ``application/schemas/`` package instead.
"""

from .pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    DeleteResponseSchema,
    ListQueryParams,
    PaginatedResponseSchema,
    ReorderItemSchema,
    ReorderRequestSchema,
    ReorderResponseSchema,
    SortOrder,
    list_query_params,
)

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "DeleteResponseSchema",
    "ListQueryParams",
    "PaginatedResponseSchema",
    "ReorderItemSchema",
    "ReorderRequestSchema",
    "ReorderResponseSchema",
    "SortOrder",
    "list_query_params",
]
