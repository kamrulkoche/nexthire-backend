"""Remotive — remote jobs, public JSON API, no key.

``GET https://remotive.com/api/remote-jobs?search=&category=&limit=``
→ ``{"jobs": [{id, url, title, company_name, category, tags, job_type,
publication_date, candidate_required_location, description}]}``

Every Remotive job is remote; its location field is where candidates must
live, kept as the location.
"""

from typing import Any, Optional

from ....domain.services.job_connector import ConnectorResult
from ..http_fetcher import HttpFetcher
from .common import build_job

API_URL = "https://remotive.com/api/remote-jobs"


class RemotiveConnector:
    """Reads Remotive."""

    def __init__(self, fetcher: Optional[HttpFetcher] = None) -> None:
        """Use the given fetcher, or a default one."""
        self.fetcher = fetcher or HttpFetcher("remotive")

    async def fetch(self, config: dict[str, Any], limit: int) -> ConnectorResult:
        """Read up to ``limit`` jobs matching the source's search and category."""
        params: dict[str, Any] = {"limit": limit}
        if config.get("search"):
            params["search"] = config["search"]
        if config.get("category"):
            params["category"] = config["category"]
        payload = await self.fetcher.get_json(API_URL, params=params)

        result = ConnectorResult()
        for item in (payload.get("jobs") if isinstance(payload, dict) else None) or []:
            if not isinstance(item, dict):
                result.skipped += 1
                continue
            job = build_job(
                external_id=item.get("id"),
                title=item.get("title"),
                company=item.get("company_name"),
                url=item.get("url"),
                description=item.get("description"),
                location=item.get("candidate_required_location"),
                is_remote=True,
                employment_type=item.get("job_type"),
                category=item.get("category"),
                tags=item.get("tags"),
                posted_at=item.get("publication_date"),
            )
            if job is None:
                result.skipped += 1
            else:
                result.jobs.append(job)
            if len(result.jobs) >= limit:
                break
        return result
