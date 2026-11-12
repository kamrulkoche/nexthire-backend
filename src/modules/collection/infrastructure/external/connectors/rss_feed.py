"""Any RSS 2.0 or Atom feed of job postings.

Parsed with ``defusedxml``, never the standard library's parser directly: the
feed is whatever an admin's URL returns, and defusedxml refuses entity
expansion and external entities (billion laughs, XXE).

RSS ``<item>`` / Atom ``<entry>`` → title, link, guid/id, description/summary,
pubDate/published, category. Feeds rarely name the company per item, so the
source's ``company`` setting is used, then the feed's own title.
"""

from typing import Any, Optional

# Element is imported for type hints only; every parse goes through defusedxml.
from xml.etree.ElementTree import Element  # nosec B405

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from src.shared.domain.exceptions.external_service_error import ExternalServiceError

from ....domain.services.job_connector import ConnectorResult
from ..http_fetcher import HttpFetcher
from .common import build_job, looks_remote

ATOM = "{http://www.w3.org/2005/Atom}"


def _text(element: Optional[Element], *names: str) -> Optional[str]:
    if element is None:
        return None
    for name in names:
        child = element.find(name)
        if child is not None and (child.text or "").strip():
            return (child.text or "").strip()
    return None


def _atom_link(entry: Element) -> Optional[str]:
    for link in entry.findall(f"{ATOM}link"):
        if link.get("rel", "alternate") == "alternate" and link.get("href"):
            return link.get("href")
    return None


class RssFeedConnector:
    """Reads an RSS or Atom feed."""

    def __init__(self, fetcher: Optional[HttpFetcher] = None) -> None:
        """Use the given fetcher, or a default one."""
        self.fetcher = fetcher or HttpFetcher("rss_feed")

    async def fetch(self, config: dict[str, Any], limit: int) -> ConnectorResult:
        """Read the feed at the source's URL."""
        body = await self.fetcher.get_bytes(
            config["url"],
            headers={"Accept": "application/rss+xml, application/atom+xml, text/xml"},
        )
        try:
            root = SafeET.fromstring(body)
        except (SafeET.ParseError, DefusedXmlException) as e:
            raise ExternalServiceError(
                "rss_feed", "Did not return a valid feed."
            ) from e

        result = ConnectorResult()
        if root.tag == f"{ATOM}feed":
            feed_title = _text(root, f"{ATOM}title")
            items = root.findall(f"{ATOM}entry")
        else:
            channel = root.find("channel")
            feed_title = _text(channel, "title")
            items = channel.findall("item") if channel is not None else []

        company = config.get("company") or feed_title

        for item in items:
            is_atom = item.tag == f"{ATOM}entry"
            title = _text(item, f"{ATOM}title") if is_atom else _text(item, "title")
            link = _atom_link(item) if is_atom else _text(item, "link")
            guid = _text(item, f"{ATOM}id") if is_atom else _text(item, "guid")
            description = (
                _text(item, f"{ATOM}content", f"{ATOM}summary")
                if is_atom
                else _text(item, "description")
            )
            posted = (
                _text(item, f"{ATOM}published", f"{ATOM}updated")
                if is_atom
                else _text(item, "pubDate")
            )
            categories = [
                (c.get("term") if is_atom else c.text) or ""
                for c in item.findall(f"{ATOM}category" if is_atom else "category")
            ]
            job = build_job(
                external_id=guid or link,
                title=title,
                company=company,
                url=link,
                description=description,
                is_remote=looks_remote(title, description),
                tags=categories,
                posted_at=posted,
            )
            if job is None:
                result.skipped += 1
            else:
                result.jobs.append(job)
            if len(result.jobs) >= limit:
                break
        return result
