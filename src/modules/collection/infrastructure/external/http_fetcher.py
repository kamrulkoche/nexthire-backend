"""Outbound HTTP for connectors.

Every connector fetches through this, so the safety rules live in one place:

- **Timeout and size cap.** A source that hangs or streams forever cannot tie
  up a worker; the body is read in chunks and abandoned past
  ``CONNECTOR_MAX_BYTES``.
- **No private addresses.** An admin can type any feed URL. Before each
  request — and each redirect hop, followed by hand for that reason — the host
  is resolved and refused if ANY address it resolves to is private, loopback,
  link-local, multicast, reserved or unspecified. That stops a feed URL from
  probing this server's own network (`http://169.254.169.254/`,
  `http://localhost:5432/`). The check runs at fetch time, not save time,
  because DNS can change in between.
- **Errors never echo the upstream body.** ``ExternalServiceError`` names the
  source and the status only.
"""

import asyncio
import ipaddress
import json
import socket
from collections.abc import Awaitable, Callable
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx

from src.shared.domain.exceptions.external_service_error import ExternalServiceError
from src.shared.infrastructure.logging import get_logger
from src.shared.utils.config import settings

logger = get_logger(__name__)

MAX_REDIRECTS = 3

Resolver = Callable[[str], Awaitable[list[str]]]


async def system_resolver(host: str) -> list[str]:
    """Resolve a host to its IP addresses with the system resolver."""
    infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    return list({str(info[4][0]) for info in infos})


def is_public_address(address: str) -> bool:
    """Whether an IP address is safe to connect to from this server."""
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


class HttpFetcher:
    """GETs a URL safely and returns its body."""

    def __init__(
        self,
        service: str,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        resolver: Optional[Resolver] = None,
    ) -> None:
        """Configure the fetcher.

        Args:
            service: Names the source in errors and logs
            transport: An httpx transport — tests pass a ``MockTransport``
            resolver: Host-to-addresses lookup — tests pass a fake
        """
        self.service = service
        self._transport = transport
        self._resolver = resolver or system_resolver

    async def _check_host(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ExternalServiceError(
                self.service, "Only http(s) URLs can be fetched."
            )
        try:
            addresses = await self._resolver(parsed.hostname)
        except OSError as e:
            raise ExternalServiceError(self.service, "The host did not resolve.") from e
        if not addresses or not all(is_public_address(a) for a in addresses):
            logger.warning(
                f"Refused non-public host for {self.service}: {parsed.hostname}"
            )
            raise ExternalServiceError(
                self.service, "The host resolves to a private or reserved address."
            )

    async def get_bytes(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> bytes:
        """GET a URL and return its body.

        Raises:
            ExternalServiceError: Unsafe host, transport error, non-2xx status,
                too many redirects, or a body over the size cap
        """
        request_headers = {"User-Agent": settings.connector_user_agent}
        request_headers.update(headers or {})
        current = url
        async with httpx.AsyncClient(
            timeout=settings.connector_timeout_seconds,
            transport=self._transport,
            follow_redirects=False,
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                await self._check_host(current)
                try:
                    async with client.stream(
                        "GET", current, params=params, headers=request_headers
                    ) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                raise ExternalServiceError(
                                    self.service, "Redirect without a location."
                                )
                            current = urljoin(str(response.url), location)
                            params = None  # already part of the redirected URL
                            continue
                        if response.status_code >= 400:
                            raise ExternalServiceError(
                                self.service, f"Answered HTTP {response.status_code}."
                            )
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > settings.connector_max_bytes:
                                raise ExternalServiceError(
                                    self.service, "The response was too large."
                                )
                        return bytes(body)
                except httpx.HTTPError as e:
                    logger.warning(
                        f"{self.service} transport error: {type(e).__name__}"
                    )
                    raise ExternalServiceError(self.service, "Request failed.") from e
        raise ExternalServiceError(self.service, "Too many redirects.")

    async def get_json(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> Any:
        """GET a URL and parse its body as JSON.

        Raises:
            ExternalServiceError: As ``get_bytes``, or the body is not JSON
        """
        body = await self.get_bytes(
            url,
            params=params,
            headers={"Accept": "application/json", **(headers or {})},
        )
        try:
            return json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ExternalServiceError(self.service, "Did not return JSON.") from e
