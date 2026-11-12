"""Any JSON endpoint of job postings, mapped through the source's ``field_map``.

The admin names where the list of postings is (``items_path``, dotted; empty
means the response itself is the list) and, for each field, the dotted path to
it inside one posting::

    {"items_path": "data.jobs",
     "field_map": {"id": "id", "title": "position", "company": "org.name",
                   "url": "links.apply", "posted_at": "created"}}

Paths only ever READ from the parsed JSON — there is no expression language to
evaluate, so a field map cannot do anything but pick values.
"""

from typing import Any, Optional

from src.shared.domain.exceptions.external_service_error import ExternalServiceError

from ....domain.services.job_connector import ConnectorResult
from ..http_fetcher import HttpFetcher
from .common import build_job, looks_remote


def pick(data: Any, path: Optional[str]) -> Any:
    """Follow a dotted path into nested dicts and lists; None if it breaks.

    A numeric segment indexes a list: ``locations.0.name``.
    """
    if not path:
        return data
    current = data
    for segment in path.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, list) and segment.isdigit():
            index = int(segment)
            current = current[index] if index < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


class JsonFeedConnector:
    """Reads a mapped JSON feed."""

    def __init__(self, fetcher: Optional[HttpFetcher] = None) -> None:
        """Use the given fetcher, or a default one."""
        self.fetcher = fetcher or HttpFetcher("json_feed")

    async def fetch(self, config: dict[str, Any], limit: int) -> ConnectorResult:
        """Read the feed and map each item."""
        payload = await self.fetcher.get_json(config["url"])
        items = pick(payload, config.get("items_path"))
        if not isinstance(items, list):
            raise ExternalServiceError(
                "json_feed", "items_path does not point at a list."
            )

        field_map: dict[str, str] = config["field_map"]
        result = ConnectorResult()
        for item in items:
            if not isinstance(item, dict):
                result.skipped += 1
                continue

            def get(key: str, _item: dict = item) -> Any:
                return pick(_item, field_map.get(key)) if key in field_map else None

            url = get("url")
            remote = get("remote")
            job = build_job(
                external_id=get("id") or url,
                title=get("title"),
                company=get("company"),
                url=url,
                description=get("description"),
                location=get("location"),
                is_remote=(
                    bool(remote)
                    if isinstance(remote, bool)
                    else looks_remote(
                        str(get("title") or ""), str(get("location") or "")
                    )
                ),
                salary_min=get("salary_min"),
                salary_max=get("salary_max"),
                tags=get("tags"),
                posted_at=get("posted_at"),
            )
            if job is None:
                result.skipped += 1
            else:
                result.jobs.append(job)
            if len(result.jobs) >= limit:
                break
        return result
