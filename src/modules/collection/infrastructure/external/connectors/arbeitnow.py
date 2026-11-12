"""Arbeitnow — European jobs board, public JSON API, no key.

``GET https://www.arbeitnow.com/api/job-board-api?page=N``
→ ``{"data": [{slug, company_name, title, description, remote, url, tags,
job_types, location, created_at}], "links": {"next": ...}}``

The API has no search parameter, so ``search`` is applied here, to the title
and tags, after reading ``max_pages`` pages.
"""

from typing import Any, Optional

from ....domain.services.job_connector import ConnectorResult
from ..http_fetcher import HttpFetcher
from .common import build_job

API_URL = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowConnector:
    """Reads Arbeitnow."""

    def __init__(self, fetcher: Optional[HttpFetcher] = None) -> None:
        """Use the given fetcher, or a default one."""
        self.fetcher = fetcher or HttpFetcher("arbeitnow")

    async def fetch(self, config: dict[str, Any], limit: int) -> ConnectorResult:
        """Read pages until ``max_pages``, ``limit`` jobs, or the last page."""
        search = (config.get("search") or "").lower()
        result = ConnectorResult()
        for page in range(1, int(config.get("max_pages", 1)) + 1):
            payload = await self.fetcher.get_json(API_URL, params={"page": page})
            items = (payload.get("data") if isinstance(payload, dict) else None) or []
            for item in items:
                if not isinstance(item, dict):
                    result.skipped += 1
                    continue
                if search:
                    haystack = " ".join(
                        [
                            str(item.get("title") or ""),
                            *map(str, item.get("tags") or []),
                        ]
                    ).lower()
                    if search not in haystack:
                        continue
                job_types = item.get("job_types") or []
                job = build_job(
                    external_id=item.get("slug"),
                    title=item.get("title"),
                    company=item.get("company_name"),
                    url=item.get("url"),
                    description=item.get("description"),
                    location=item.get("location"),
                    is_remote=bool(item.get("remote")),
                    employment_type=job_types[0] if job_types else None,
                    tags=item.get("tags"),
                    posted_at=item.get("created_at"),
                )
                if job is None:
                    result.skipped += 1
                else:
                    result.jobs.append(job)
                if len(result.jobs) >= limit:
                    return result
            links = payload.get("links") if isinstance(payload, dict) else None
            if not items or not (isinstance(links, dict) and links.get("next")):
                break
        return result
