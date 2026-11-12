"""Source type → connector.

The one place that knows which class reads which type. Tests replace an entry
in ``CONNECTORS`` with a fake to run a collection without the network.
"""

from collections.abc import Callable

from src.modules.job_source.domain.enums.source_type import SourceType

from ....domain.services.job_connector import JobConnector
from .adzuna import AdzunaConnector
from .arbeitnow import ArbeitnowConnector
from .json_feed import JsonFeedConnector
from .remoteok import RemoteOkConnector
from .remotive import RemotiveConnector
from .rss_feed import RssFeedConnector

CONNECTORS: dict[SourceType, Callable[[], JobConnector]] = {
    SourceType.REMOTIVE: RemotiveConnector,
    SourceType.ARBEITNOW: ArbeitnowConnector,
    SourceType.REMOTEOK: RemoteOkConnector,
    SourceType.ADZUNA: AdzunaConnector,
    SourceType.RSS_FEED: RssFeedConnector,
    SourceType.JSON_FEED: JsonFeedConnector,
}


def connector_for(source_type: SourceType) -> JobConnector:
    """A fresh connector for this source type."""
    return CONNECTORS[source_type]()
