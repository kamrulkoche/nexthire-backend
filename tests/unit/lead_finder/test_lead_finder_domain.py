"""Lead Finder units: phone normalization, location resolution, the Places
client (parsing, retries, error mapping) — no network."""

import json
from typing import Any

import httpx
import pytest

from src.modules.lead_finder.domain.services.bangladesh_locations import (
    LocationSelection,
    UnknownLocationError,
    describe_selection,
    district_count,
    resolve_targets,
    selections_from_stored,
    summarize_selection,
)
from src.modules.lead_finder.domain.services.phone import normalize_phone
from src.modules.lead_finder.infrastructure.external.google_places_client import (
    TEXT_SEARCH_FIELD_MASK,
    GooglePlacesClient,
    PlacesApiError,
    PlacesNotConfiguredError,
)

# ------------------------------------------------------------------- phones


@pytest.mark.parametrize(
    ("national", "international", "expected"),
    [
        ("01712-345678", None, "+8801712345678"),
        (None, "+880 1712-345678", "+8801712345678"),
        ("02-55012345", None, "+880255012345"),
        ("+880 2-9876543", None, "+88029876543"),
        ("1712345678", None, "+8801712345678"),
        (None, None, None),
        ("", None, None),
        ("123", None, None),
    ],
)
def test_normalize_phone(national: Any, international: Any, expected: Any) -> None:
    assert normalize_phone(national, international) == expected


# ---------------------------------------------------------------- locations


def test_hierarchy_has_every_district() -> None:
    assert district_count() == 64


def test_all_bangladesh_is_every_district() -> None:
    targets = resolve_targets([])
    assert len(targets) == 64
    assert targets[0].query("Hotel").endswith("District, Bangladesh")


def test_division_expands_to_its_districts() -> None:
    targets = resolve_targets([LocationSelection(division="sylhet")])
    assert sorted(t.district for t in targets) == [
        "Habiganj",
        "Moulvibazar",
        "Sunamganj",
        "Sylhet",
    ]


def test_area_query_and_dedup() -> None:
    selection = LocationSelection("dhaka", "dhaka", "savar", " Ashulia ")
    targets = resolve_targets([selection, selection])
    assert len(targets) == 1
    assert (
        targets[0].query("Hospital") == "Hospital in Ashulia, Savar, Dhaka, Bangladesh"
    )


@pytest.mark.parametrize(
    "selection",
    [
        LocationSelection(division="atlantis"),
        LocationSelection(division="dhaka", district="sylhet"),
        LocationSelection(division="dhaka", district="dhaka", upazila="nowhere"),
        LocationSelection(division="dhaka", district="dhaka", area="Ashulia"),
        LocationSelection(district="dhaka"),
    ],
)
def test_unknown_or_orphan_locations_are_refused(selection: LocationSelection) -> None:
    with pytest.raises(UnknownLocationError):
        resolve_targets([selection])


def test_area_text_is_sanitized_for_the_query() -> None:
    selection = LocationSelection("dhaka", "dhaka", "savar", "Ashulia<script>")
    assert resolve_targets([selection])[0].area == "Ashulia script"


def test_stored_selection_round_trips() -> None:
    selections = [LocationSelection("dhaka", "gazipur"), LocationSelection("khulna")]
    described = describe_selection(selections)
    assert summarize_selection(described) == "Gazipur +1 more"
    assert resolve_targets(selections_from_stored(described)) == resolve_targets(
        selections
    )


# -------------------------------------------------------------- places API

PLACE = {
    "id": "ChIJ123",
    "displayName": {"text": "Ashulia Hospital", "languageCode": "en"},
    "primaryTypeDisplayName": {"text": "Hospital"},
    "primaryType": "hospital",
    "types": ["hospital", "health"],
    "rating": 4.2,
    "userRatingCount": 87,
    "formattedAddress": "Ashulia, Savar",
    "nationalPhoneNumber": "01712-345678",
    "internationalPhoneNumber": "+880 1712-345678",
    "googleMapsUri": "https://maps.google.com/?cid=1",
    "location": {"latitude": 23.9, "longitude": 90.3},
    "regularOpeningHours": {"weekdayDescriptions": ["Monday: Open 24 hours"]},
    "businessStatus": "OPERATIONAL",
}


async def _no_sleep(_: float) -> None:
    return None


def _client(handler: Any, **kwargs: Any) -> GooglePlacesClient:
    return GooglePlacesClient(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
        **kwargs,
    )


async def test_text_search_sends_key_in_header_and_parses_places() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"places": [PLACE, {"no": "id"}], "nextPageToken": "t2"}
        )

    client = _client(handler)
    places, token = await client.text_search("Hospital in Savar, Dhaka, Bangladesh")

    assert seen["url"].endswith("/v1/places:searchText")
    assert "test-key" not in seen["url"]
    assert seen["headers"]["x-goog-api-key"] == "test-key"
    assert seen["headers"]["x-goog-fieldmask"] == TEXT_SEARCH_FIELD_MASK
    assert seen["body"]["regionCode"] == "BD"
    assert "locationRestriction" in seen["body"]
    assert token == "t2"
    assert len(places) == 1
    record = places[0]
    assert record.name == "Ashulia Hospital"
    assert record.phone_display == "01712-345678"
    assert record.website_uri is None
    assert record.review_count == 87
    assert record.opening_hours == ["Monday: Open 24 hours"]
    assert client.requests_made == 1


async def test_retries_rate_limits_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"places": [PLACE]})

    client = _client(handler, max_attempts=3)
    places, token = await client.text_search("q")
    assert len(places) == 1 and token is None
    assert client.requests_made == 3


async def test_refused_key_is_not_retried_and_message_is_safe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "secret detail key=abc"}})

    client = _client(handler, max_attempts=3)
    with pytest.raises(PlacesApiError) as raised:
        await client.text_search("q")
    assert raised.value.status == 403
    assert "abc" not in raised.value.message
    assert client.requests_made == 1


async def test_transport_errors_are_retried_then_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    client = _client(handler, max_attempts=2)
    with pytest.raises(PlacesApiError) as raised:
        await client.text_search("q")
    assert raised.value.status == 0
    assert client.requests_made == 2


async def test_details_returns_none_when_google_has_no_such_place() -> None:
    client = _client(lambda request: httpx.Response(404, json={}))
    assert await client.place_details("gone") is None


async def test_no_key_is_reported_before_any_request() -> None:
    client = GooglePlacesClient(
        api_key="", transport=httpx.MockTransport(lambda r: httpx.Response(200))
    )
    with pytest.raises(PlacesNotConfiguredError):
        await client.text_search("q")
    assert client.requests_made == 0
