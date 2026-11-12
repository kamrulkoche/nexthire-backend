"""API dependencies and dependency injection."""

from typing import Generator

from ..shared.infrastructure.database import MongoSession, get_db


def get_database() -> Generator[MongoSession, None, None]:
    """Get database session dependency.

    Yields:
        Database session
    """
    yield from get_db()
