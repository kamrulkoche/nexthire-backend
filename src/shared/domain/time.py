"""Time helpers shared by every module.

All timestamps in this service are UTC. Postgres returns them timezone-aware;
SQLite (the integration suite) returns them NAIVE, and comparing a naive value
with an aware one raises ``TypeError``. ``as_utc`` makes either safe to compare.
"""

from datetime import UTC, datetime
from typing import Optional


def utc_now() -> datetime:
    """The current time, timezone-aware, in UTC."""
    return datetime.now(UTC)


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Treat a naive datetime as UTC; leave an aware one alone.

    Args:
        value: A datetime read from the database, or None

    Returns:
        The same instant, timezone-aware, or None
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
