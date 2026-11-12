"""Adzuna — multi-country aggregator, needs a free app id and key.

``GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}
?app_id=&app_key=&results_per_page=50&what=&where=``
→ ``{"results": [{id, title, company: {display_name}, location: {display_name},
description, redirect_url, created, salary_min, salary_max, contract_time,
contract_type, category: {label}}]}``

The credentials come from ``ADZUNA_APP_ID`` / ``ADZUNA_APP_KEY`` in the
environment — never from the source's config, which the admin screen shows.
"""

from typing import Any, Optional

from src.shared.domain.exceptions.external_service_error import ExternalServiceError
from src.shared.utils.config import settings

from ....domain.services.job_connector import ConnectorResult
from ..http_fetcher import HttpFetcher
from .common import build_job, looks_remote

API_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"

RESULTS_PER_PAGE = 50

#: Adzuna reports salaries in the country's currency.
CURRENCY_BY_COUNTRY = {
    "gb": "GBP",
    "us": "USD",
    "ca": "CAD",
    "au": "AUD",
    "nz": "NZD",
    "in": "INR",
    "sg": "SGD",
    "za": "ZAR",
    "br": "BRL",
    "mx": "MXN",
    "pl": "PLN",
    "ch": "CHF",
}


def _display(value: Any) -> Optional[str]:
    return value.get("display_name") if isinstance(value, dict) else None


class AdzunaConnector:
    """Reads Adzuna."""

    def __init__(
        self,
        fetcher: Optional[HttpFetcher] = None,
        app_id: Optional[str] = None,
        app_key: Optional[str] = None,
    ) -> None:
        """Use the given fetcher and credentials, or the defaults."""
        self.fetcher = fetcher or HttpFetcher("adzuna")
        self.app_id = app_id if app_id is not None else settings.adzuna_app_id
        self.app_key = app_key if app_key is not None else settings.adzuna_app_key

    async def fetch(self, config: dict[str, Any], limit: int) -> ConnectorResult:
        """Read up to ``max_pages`` pages of search results."""
        if not (self.app_id and self.app_key):
            raise ExternalServiceError(
                "adzuna", "ADZUNA_APP_ID and ADZUNA_APP_KEY are not set."
            )
        country = config["country"]
        currency = CURRENCY_BY_COUNTRY.get(country, "EUR")
        result = ConnectorResult()
        for page in range(1, int(config.get("max_pages", 1)) + 1):
            params: dict[str, Any] = {
                "app_id": self.app_id,
                "app_key": self.app_key,
                "results_per_page": RESULTS_PER_PAGE,
                "content-type": "application/json",
            }
            if config.get("what"):
                params["what"] = config["what"]
            if config.get("where"):
                params["where"] = config["where"]
            payload = await self.fetcher.get_json(
                API_URL.format(country=country, page=page), params=params
            )
            items = (
                payload.get("results") if isinstance(payload, dict) else None
            ) or []
            for item in items:
                if not isinstance(item, dict):
                    result.skipped += 1
                    continue
                location = _display(item.get("location"))
                category = item.get("category")
                job = build_job(
                    external_id=item.get("id"),
                    title=item.get("title"),
                    company=_display(item.get("company")),
                    url=item.get("redirect_url"),
                    description=item.get("description"),
                    location=location,
                    is_remote=looks_remote(item.get("title"), location),
                    employment_type=item.get("contract_type")
                    or item.get("contract_time"),
                    salary_min=item.get("salary_min"),
                    salary_max=item.get("salary_max"),
                    salary_currency=currency,
                    category=category.get("label")
                    if isinstance(category, dict)
                    else None,
                    posted_at=item.get("created"),
                )
                if job is None:
                    result.skipped += 1
                else:
                    result.jobs.append(job)
                if len(result.jobs) >= limit:
                    return result
            if len(items) < RESULTS_PER_PAGE:
                break
        return result
