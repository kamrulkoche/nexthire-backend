"""Parsing helpers every connector shares.

Sources disagree about everything: dates come as ISO strings, Unix seconds or
RFC 822; salaries as numbers, strings or nothing; tags as lists or commas.
These helpers turn each into one shape and return None rather than raising on
garbage, so one odd field never costs a whole posting.
"""

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Iterable, Optional

from src.modules.job.domain.enums.employment_type import EmploymentType
from src.shared.domain.text import clip, strip_html

from ....domain.value_objects.collected_job import CollectedJob

_REMOTE = re.compile(r"\b(remote|anywhere|worldwide|work from home|wfh)\b", re.I)


def parse_datetime(value: Any) -> Optional[datetime]:
    """ISO 8601, Unix seconds or RFC 822, to an aware UTC datetime."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(float(value), tz=UTC)
        text = str(value).strip()
        if text.isdigit():
            return datetime.fromtimestamp(float(text), tz=UTC)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        parsed = parsed.astimezone(UTC)
        # A date from the future is a source error; trust "now" over it.
        return min(parsed, datetime.now(UTC))
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def parse_int(value: Any) -> Optional[int]:
    """A positive whole number from a number or a numeric string, else None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(float(str(value).replace(",", "").strip()))
    except (ValueError, TypeError, OverflowError):
        return None
    return number if 0 < number < 100_000_000 else None


def parse_tags(value: Any) -> tuple[str, ...]:
    """Tags from a list or a comma-separated string, trimmed, deduplicated."""
    if value is None:
        return ()
    items: Iterable[Any] = (
        value if isinstance(value, (list, tuple)) else str(value).split(",")
    )
    seen: dict[str, str] = {}
    for item in items:
        if isinstance(item, dict):
            item = item.get("name") or item.get("term") or ""
        tag = clip(str(item), 40)
        if tag and tag.lower() not in seen:
            seen[tag.lower()] = tag
    return tuple(list(seen.values())[:15])


def looks_remote(*texts: Optional[str]) -> bool:
    """Whether any of the texts says the job is remote."""
    return any(_REMOTE.search(text) for text in texts if text)


def build_job(
    *,
    external_id: Any,
    title: Any,
    company: Any,
    url: Any,
    description: Any = None,
    location: Any = None,
    is_remote: bool = False,
    employment_type: Any = None,
    salary_min: Any = None,
    salary_max: Any = None,
    salary_currency: Optional[str] = None,
    category: Any = None,
    tags: Any = None,
    posted_at: Any = None,
) -> Optional[CollectedJob]:
    """Normalize raw fields into a ``CollectedJob``, or None if unusable.

    A posting needs an id, a title, a company and an http(s) URL; anything
    less is skipped. Text is HTML-stripped and clipped to its column.
    """
    clean_id = clip(str(external_id) if external_id is not None else None, 255)
    clean_title = clip(strip_html(str(title)) if title else None, 300)
    clean_company = clip(strip_html(str(company)) if company else None, 200)
    clean_url = clip(str(url) if url else None, 1000)
    if not (clean_id and clean_title and clean_company and clean_url):
        return None
    if not clean_url.lower().startswith(("http://", "https://")):
        return None

    low = parse_int(salary_min)
    high = parse_int(salary_max)
    if low and high and low > high:
        low, high = high, low

    return CollectedJob(
        external_id=clean_id,
        title=clean_title,
        company=clean_company,
        url=clean_url,
        description=strip_html(str(description)) if description else "",
        location=clip(strip_html(str(location)) if location else None, 200),
        is_remote=is_remote,
        employment_type=(
            employment_type
            if isinstance(employment_type, EmploymentType)
            else EmploymentType.from_source(employment_type)
        ),
        salary_min=low,
        salary_max=high,
        salary_currency=(salary_currency or None) if (low or high) else None,
        category=clip(str(category) if category else None, 120),
        tags=parse_tags(tags),
        posted_at=parse_datetime(posted_at),
    )
