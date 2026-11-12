"""Turning a client-supplied sort key into a sort field, safely — plus the
small MongoDB query helpers every repository shares.
"""

import re
from typing import Any, Optional, Set

from pymongo import ASCENDING, DESCENDING


def resolve_sort_column(
    requested: Optional[str],
    allowed: Set[str],
    default: str,
) -> str:
    """Turn a client-supplied sort name into a field name, safely.

    The sort key arrives in a query string, and sorting by any field a caller
    names would let them order by fields a public schema deliberately omits,
    which leaks their values through the ordering. An allowlist per resource
    is the fix.

    An unknown name falls back to the default rather than erroring: it is
    usually a stale bookmark, and a 422 for that helps nobody.

    Returns:
        The document field to sort by (``id`` is mapped to ``_id``)
    """
    name = requested if requested is not None and requested in allowed else default
    return "_id" if name == "id" else name


def sort_spec(
    field: str, order: Optional[str], *tiebreakers: str
) -> list[tuple[str, int]]:
    """A PyMongo sort list: ``field`` by ``order`` then ascending tiebreakers."""
    direction = DESCENDING if order == "desc" else ASCENDING
    spec = [(field, direction)]
    spec.extend((t, ASCENDING) for t in tiebreakers if t != field)
    return spec


def contains_ci(term: str) -> dict[str, Any]:
    """A case-insensitive substring match — the MongoDB form of ``ILIKE '%term%'``.

    The term is escaped, so a user's ``.*`` is matched literally and never
    becomes a regular expression.
    """
    return {"$regex": re.escape(term), "$options": "i"}


def equals_ci(term: str) -> dict[str, Any]:
    """A case-insensitive whole-value match — ``lower(col) = lower(term)``."""
    return {"$regex": f"^{re.escape(term)}$", "$options": "i"}
