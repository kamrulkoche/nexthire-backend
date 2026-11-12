"""User domain entities.

Imported by `database.discover_entities()` so every collection's indexes are
registered before `ensure_indexes` runs.
"""

from .user import User

__all__ = ["User"]
