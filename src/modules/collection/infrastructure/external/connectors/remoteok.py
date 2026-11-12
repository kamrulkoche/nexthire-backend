"""Remote OK — remote jobs, public JSON API, no key.

``GET https://remoteok.com/api`` (optionally ``?tag=python``) → a list whose
FIRST element is a legal notice, not a job; the rest are
``{id, epoch, company, position, tags, description, location, salary_min,
salary_max, url, apply_url}``.

Remote OK's terms ask that jobs link back to it, which ``url`` does. It
rejects requests without a User-Agent; the fetcher always sends one.
"""

from typing import Any, Optional

from ....domain.services.job_connector import ConnectorResult
from ..http_fetcher import HttpFetcher
from .common import build_job

API_URL = "https://remoteok.com/api"


class RemoteOkConnector:
    """Reads Remote OK."""

    def __init__(self, fetcher: Optional[HttpFetcher] = None) -> None:
        """Use the given fetcher, or a default one."""
        self.fetcher = fetcher or HttpFetcher("remoteok")

    async def fetch(self, config: dict[str, Any], limit: int) -> ConnectorResult:
        """Read the feed, optionally narrowed to one tag."""
        params = {"tag": config["tag"]} if config.get("tag") else None
        payload = await self.fetcher.get_json(API_URL, params=params)

        result = ConnectorResult()
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict) or "legal" in item:
                continue
            job = build_job(
                external_id=item.get("id"),
                title=item.get("position"),
                company=item.get("company"),
                url=item.get("url") or item.get("apply_url"),
                description=item.get("description"),
                location=item.get("location") or None,
                is_remote=True,
                salary_min=item.get("salary_min"),
                salary_max=item.get("salary_max"),
                salary_currency="USD",
                tags=item.get("tags"),
                posted_at=item.get("epoch") or item.get("date"),
            )
            if job is None:
                result.skipped += 1
            else:
                result.jobs.append(job)
            if len(result.jobs) >= limit:
                break
        return result
