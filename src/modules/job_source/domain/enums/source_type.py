"""Job source type enum."""

from enum import Enum


class SourceType(str, Enum):
    """
    Which connector reads a source.

    Each value has exactly one connector class in
    ``collection/infrastructure/external/connectors/`` and one config rule in
    ``job_source/domain/services/source_config.py``. Adding a type means adding
    both, a migration for the enum value, and the frontend's label.

    - REMOTIVE, ARBEITNOW, REMOTEOK: public JSON APIs, no credentials
    - ADZUNA: needs ADZUNA_APP_ID / ADZUNA_APP_KEY in the environment
    - RSS_FEED: any RSS 2.0 or Atom feed of postings
    - JSON_FEED: any JSON endpoint, mapped through the source's ``field_map``
    """

    REMOTIVE = "remotive"
    ARBEITNOW = "arbeitnow"
    REMOTEOK = "remoteok"
    ADZUNA = "adzuna"
    RSS_FEED = "rss_feed"
    JSON_FEED = "json_feed"

    @classmethod
    def all_types(cls) -> list[str]:
        """Return all valid type values."""
        return [t.value for t in cls]
