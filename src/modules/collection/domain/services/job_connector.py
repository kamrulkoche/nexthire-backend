"""The connector contract.

One implementation per ``SourceType``, in
``infrastructure/external/connectors/``. A connector reads its source and
returns normalized ``CollectedJob`` values; it does no database work and
raises ``ExternalServiceError`` when the source cannot be read at all.

A connector may skip individual malformed postings — it reports how many in
``ConnectorResult.skipped`` — because one bad row in a feed of five hundred
should not fail the whole run.
"""

from dataclasses import dataclass, field
from typing import Any, List, Protocol

from ..value_objects.collected_job import CollectedJob


@dataclass
class ConnectorResult:
    """What a connector read."""

    jobs: List[CollectedJob] = field(default_factory=list)
    skipped: int = 0


class JobConnector(Protocol):
    """Reads one source type."""

    async def fetch(self, config: dict[str, Any], limit: int) -> ConnectorResult:
        """Read the source.

        Args:
            config: The source's normalized config (see ``source_config.py``)
            limit: Most jobs to return

        Returns:
            The postings read, and how many were skipped as malformed

        Raises:
            ExternalServiceError: The source could not be read
        """
        ...
