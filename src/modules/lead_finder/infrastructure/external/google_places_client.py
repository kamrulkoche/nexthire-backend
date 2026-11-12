"""Google Maps Platform — Places API (New). The only code that calls Google.

Two endpoints, both official and supported:

- Text Search: ``POST /v1/places:searchText``. One query ("Hospital in Savar,
  Dhaka, Bangladesh"), up to 20 places a page, up to 3 pages (60 places) via
  ``nextPageToken``. With the field mask below it already carries phone,
  website, rating, hours and location, so a search needs no per-place follow
  up call.
- Place Details: ``GET /v1/places/{place_id}``. Used to REFRESH a lead whose
  stored content expired or that the user wants re-read.

No scraping of Google Maps pages, ever: everything comes from these two.

The key travels in the ``X-Goog-Api-Key`` header, never the URL, so it cannot
end up in an access log, and error messages never echo Google's response body.

Retries: a 429, a 5xx or a transport error is retried with exponential backoff
(``PLACES_MAX_ATTEMPTS`` attempts, honouring ``Retry-After`` up to a ceiling).
A 4xx other than 429 is the request's or the key's fault and is not retried.

Every HTTP attempt increments ``requests_made``, which is what the daily quota
and the per-search cap count.
"""

import asyncio
import random
from typing import Any, List, Optional, Tuple
from urllib.parse import quote

import httpx

from src.shared.domain.exceptions.external_service_error import ExternalServiceError
from src.shared.infrastructure.logging import get_logger
from src.shared.utils.config import settings

from ...domain.value_objects.place_record import PlaceRecord

logger = get_logger(__name__)

PLACES_BASE_URL = "https://places.googleapis.com/v1"
SERVICE_NAME = "Google Places"

#: Bangladesh's bounding box. Text Search is RESTRICTED to it, so "Hospital in
#: Kaliganj" can never return a Kaliganj in another country.
BANGLADESH_RECTANGLE = {
    "low": {"latitude": 20.55, "longitude": 88.0},
    "high": {"latitude": 26.65, "longitude": 92.70},
}

#: The place fields requested. Listing them is mandatory (no default mask) and
#: it is also what Google bills by, so nothing is requested that is not shown.
PLACE_FIELDS = (
    "id",
    "displayName",
    "primaryTypeDisplayName",
    "primaryType",
    "types",
    "rating",
    "userRatingCount",
    "formattedAddress",
    "nationalPhoneNumber",
    "internationalPhoneNumber",
    "websiteUri",
    "googleMapsUri",
    "location",
    "regularOpeningHours.weekdayDescriptions",
    "businessStatus",
)

TEXT_SEARCH_FIELD_MASK = ",".join(
    [f"places.{name}" for name in PLACE_FIELDS] + ["nextPageToken"]
)
DETAILS_FIELD_MASK = ",".join(PLACE_FIELDS)

#: Statuses worth another attempt.
_RETRYABLE = {429, 500, 502, 503, 504}

#: Longest single wait between attempts, whatever Retry-After says.
_MAX_BACKOFF_SECONDS = 8.0

#: What the user is told for each failure, keyed by HTTP status.
_MESSAGES = {
    400: "Google rejected the search request. Try a simpler keyword.",
    401: "The Google Maps API key is invalid.",
    403: (
        "Google refused the API key. Check that it is valid and that "
        "Places API (New) is enabled for it in Google Cloud."
    ),
    404: "Google has no place with that ID.",
    429: "Google Places quota or rate limit reached. Try again in a few minutes.",
}


class PlacesApiError(ExternalServiceError):
    """A Places call failed. ``status`` is the HTTP status (0 for transport)."""

    def __init__(self, status: int, message: str):
        """Initialize with the HTTP status and a safe message."""
        self.status = status
        super().__init__(SERVICE_NAME, message)


class PlacesNotConfiguredError(ExternalServiceError):
    """No ``GOOGLE_MAPS_API_KEY`` is set."""

    def __init__(self) -> None:
        """Initialize with the setup hint."""
        super().__init__(
            SERVICE_NAME,
            "The Google Maps API key is not configured. Set GOOGLE_MAPS_API_KEY "
            "in nexthire-backend/.env (with Places API (New) enabled) and restart "
            "the backend.",
        )


def _parse_place(raw: dict[str, Any]) -> Optional[PlaceRecord]:
    """Flatten one Places API ``Place`` object. None if it has no ID."""
    place_id = raw.get("id")
    if not isinstance(place_id, str) or not place_id:
        return None
    display = raw.get("displayName") or {}
    category = raw.get("primaryTypeDisplayName") or {}
    location = raw.get("location") or {}
    hours = (raw.get("regularOpeningHours") or {}).get("weekdayDescriptions") or []
    rating = raw.get("rating")
    reviews = raw.get("userRatingCount")

    def text(value: Any) -> Optional[str]:
        return value.strip() or None if isinstance(value, str) else None

    def number(value: Any) -> Optional[float]:
        return float(value) if isinstance(value, (int, float)) else None

    return PlaceRecord(
        place_id=place_id,
        name=text(display.get("text")),
        primary_category=text(category.get("text")),
        primary_type=text(raw.get("primaryType")),
        types=[t for t in raw.get("types") or [] if isinstance(t, str)][:20],
        rating=number(rating),
        review_count=int(reviews) if isinstance(reviews, int) else None,
        formatted_address=text(raw.get("formattedAddress")),
        phone_display=text(raw.get("nationalPhoneNumber")),
        phone_international=text(raw.get("internationalPhoneNumber")),
        website_uri=text(raw.get("websiteUri")),
        google_maps_uri=text(raw.get("googleMapsUri")),
        latitude=number(location.get("latitude")),
        longitude=number(location.get("longitude")),
        opening_hours=[h for h in hours if isinstance(h, str)][:7],
        business_status=text(raw.get("businessStatus")),
    )


class GooglePlacesClient:
    """Text Search and Place Details, with retries and request counting."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        timeout_seconds: Optional[float] = None,
        max_attempts: Optional[int] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        sleep: Any = asyncio.sleep,
    ) -> None:
        """Configure the client. Defaults come from settings.

        Args:
            api_key: Server-side Google Maps Platform key
            timeout_seconds: Per-request timeout
            max_attempts: Attempts per call, retries included
            transport: An httpx transport — tests pass a ``MockTransport``
            sleep: The backoff sleep — tests pass a no-op
        """
        self.api_key = api_key if api_key is not None else settings.google_maps_api_key
        self.timeout_seconds = timeout_seconds or settings.places_timeout_seconds
        self.max_attempts = max(1, max_attempts or settings.places_max_attempts)
        self._transport = transport
        self._sleep = sleep
        #: HTTP attempts made by this instance, retries included.
        self.requests_made = 0

    @property
    def is_configured(self) -> bool:
        """Whether a key is present."""
        return bool(self.api_key)

    async def text_search(
        self, query: str, page_token: Optional[str] = None
    ) -> Tuple[List[PlaceRecord], Optional[str]]:
        """One page of Text Search results.

        Args:
            query: e.g. "Hospital in Savar, Dhaka, Bangladesh"
            page_token: ``nextPageToken`` from the previous page

        Returns:
            ``(places, next_page_token)``; the token is None on the last page

        Raises:
            PlacesNotConfiguredError: No key
            PlacesApiError: Google refused or could not be reached
        """
        body: dict[str, Any] = {
            "textQuery": query,
            "pageSize": 20,
            "regionCode": "BD",
            "languageCode": "en",
            "locationRestriction": {"rectangle": BANGLADESH_RECTANGLE},
        }
        if page_token:
            body["pageToken"] = page_token
        payload = await self._request(
            "POST", f"{PLACES_BASE_URL}/places:searchText", TEXT_SEARCH_FIELD_MASK, body
        )
        places = [
            place
            for raw in payload.get("places") or []
            if isinstance(raw, dict) and (place := _parse_place(raw)) is not None
        ]
        token = payload.get("nextPageToken")
        return places, token if isinstance(token, str) and token else None

    async def place_details(self, place_id: str) -> Optional[PlaceRecord]:
        """Re-read one place. None when Google no longer has it.

        Raises:
            PlacesNotConfiguredError: No key
            PlacesApiError: Any failure other than "not found"
        """
        try:
            payload = await self._request(
                "GET",
                f"{PLACES_BASE_URL}/places/{quote(place_id, safe='')}",
                DETAILS_FIELD_MASK,
            )
        except PlacesApiError as e:
            if e.status == 404:
                return None
            raise
        return _parse_place(payload)

    async def _request(
        self,
        method: str,
        url: str,
        field_mask: str,
        body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Send with retries; return the parsed JSON body."""
        if not self.is_configured:
            raise PlacesNotConfiguredError()

        headers = {
            "X-Goog-Api-Key": str(self.api_key),
            "X-Goog-FieldMask": field_mask,
        }
        last_error: Optional[PlacesApiError] = None

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds, transport=self._transport
        ) as client:
            for attempt in range(1, self.max_attempts + 1):
                self.requests_made += 1
                retry_after: Optional[float] = None
                try:
                    response = await client.request(
                        method, url, headers=headers, json=body
                    )
                except httpx.HTTPError as e:
                    logger.warning(
                        f"Places transport error ({type(e).__name__}), "
                        f"attempt {attempt}/{self.max_attempts}"
                    )
                    last_error = PlacesApiError(
                        0, "Could not reach Google Places. Check the connection."
                    )
                else:
                    if response.status_code < 400:
                        try:
                            data = response.json()
                        except ValueError:
                            raise PlacesApiError(
                                502, "Google Places returned an unreadable answer."
                            ) from None
                        return data if isinstance(data, dict) else {}

                    status = response.status_code
                    # Log the status only: error bodies can be verbose and are
                    # not ours to repeat.
                    logger.warning(
                        f"Places answered HTTP {status}, "
                        f"attempt {attempt}/{self.max_attempts}"
                    )
                    last_error = PlacesApiError(
                        status,
                        _MESSAGES.get(
                            status, "Google Places is unavailable right now."
                        ),
                    )
                    if status not in _RETRYABLE:
                        raise last_error
                    header = response.headers.get("retry-after")
                    if header and header.isdigit():
                        retry_after = float(header)

                if attempt < self.max_attempts:
                    backoff = retry_after or (0.5 * 2 ** (attempt - 1))
                    jitter = random.uniform(0, 0.25)  # nosec B311
                    await self._sleep(min(backoff, _MAX_BACKOFF_SECONDS) + jitter)

        assert last_error is not None
        raise last_error
