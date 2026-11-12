"""Unit tests for the connectors and the fetcher behind them.

Every request goes through an ``httpx.MockTransport`` and a fake resolver, so
nothing here touches the network.
"""

import json
from typing import Any, Callable

import httpx
import pytest

from src.modules.collection.infrastructure.external.connectors.adzuna import (
    AdzunaConnector,
)
from src.modules.collection.infrastructure.external.connectors.arbeitnow import (
    ArbeitnowConnector,
)
from src.modules.collection.infrastructure.external.connectors.json_feed import (
    JsonFeedConnector,
    pick,
)
from src.modules.collection.infrastructure.external.connectors.remoteok import (
    RemoteOkConnector,
)
from src.modules.collection.infrastructure.external.connectors.remotive import (
    RemotiveConnector,
)
from src.modules.collection.infrastructure.external.connectors.rss_feed import (
    RssFeedConnector,
)
from src.modules.collection.infrastructure.external.http_fetcher import (
    HttpFetcher,
    is_public_address,
)
from src.modules.job.domain.enums.employment_type import EmploymentType
from src.shared.domain.exceptions.external_service_error import ExternalServiceError

PUBLIC_IP = "93.184.216.34"


async def public_resolver(host: str) -> list[str]:
    return [PUBLIC_IP]


def fetcher_for(
    handler: Callable[[httpx.Request], httpx.Response], resolver=public_resolver
):
    return HttpFetcher(
        "test", transport=httpx.MockTransport(handler), resolver=resolver
    )


def json_response(
    payload: Any, status: int = 200
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return handler


@pytest.mark.unit
class TestFetcherSafety:
    @pytest.mark.parametrize(
        "address, public",
        [
            ("93.184.216.34", True),
            ("127.0.0.1", False),
            ("10.0.0.5", False),
            ("192.168.1.1", False),
            ("169.254.169.254", False),
            ("::1", False),
            ("::ffff:127.0.0.1", False),
            ("0.0.0.0", False),
        ],
    )
    def test_address_classification(self, address: str, public: bool):
        assert is_public_address(address) is public

    async def test_private_host_is_refused_before_any_request(self):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={})

        async def metadata_resolver(host: str) -> list[str]:
            return ["169.254.169.254"]

        with pytest.raises(ExternalServiceError, match="private"):
            await fetcher_for(handler, metadata_resolver).get_json(
                "http://metadata.internal/"
            )
        assert requests == []

    async def test_a_redirect_to_a_private_host_is_refused(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "feeds.example.com":
                return httpx.Response(
                    302, headers={"location": "http://internal.example/x"}
                )
            return httpx.Response(200, json={})

        async def resolver(host: str) -> list[str]:
            return [PUBLIC_IP] if host == "feeds.example.com" else ["10.1.2.3"]

        with pytest.raises(ExternalServiceError, match="private"):
            await fetcher_for(handler, resolver).get_json(
                "https://feeds.example.com/jobs"
            )

    async def test_oversized_body_is_refused(self, monkeypatch: pytest.MonkeyPatch):
        from src.shared.utils.config import settings

        monkeypatch.setattr(settings, "connector_max_bytes", 1024)
        handler = lambda request: httpx.Response(200, content=b"x" * 5000)  # noqa: E731
        with pytest.raises(ExternalServiceError, match="too large"):
            await fetcher_for(handler).get_bytes("https://example.com/")

    async def test_error_status_does_not_echo_the_body(self):
        handler = lambda request: httpx.Response(500, text="secret-key=abc")  # noqa: E731
        with pytest.raises(ExternalServiceError) as caught:
            await fetcher_for(handler).get_json("https://example.com/")
        assert "500" in caught.value.message
        assert "secret" not in caught.value.message

    async def test_sends_a_user_agent(self):
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["ua"] = request.headers.get("user-agent", "")
            return httpx.Response(200, json=[])

        await fetcher_for(handler).get_json("https://example.com/")
        assert seen["ua"].startswith("NextHireAI/")


@pytest.mark.unit
class TestRemotive:
    async def test_maps_fields_and_strips_html(self):
        payload = {
            "jobs": [
                {
                    "id": 101,
                    "url": "https://remotive.com/jobs/101",
                    "title": "Python <b>Engineer</b>",
                    "company_name": "Acme",
                    "category": "Software Development",
                    "tags": ["python", "django"],
                    "job_type": "full_time",
                    "publication_date": "2026-10-01T10:00:00",
                    "candidate_required_location": "Europe",
                    "description": "<p>Build <script>x()</script>APIs</p>",
                },
                {
                    "id": 102,
                    "title": "No company",
                    "url": "https://remotive.com/jobs/102",
                },
            ]
        }
        result = await RemotiveConnector(fetcher_for(json_response(payload))).fetch(
            {"search": "python"}, 50
        )
        assert result.skipped == 1
        job = result.jobs[0]
        assert (job.external_id, job.title, job.company) == (
            "101",
            "Python Engineer",
            "Acme",
        )
        assert job.is_remote is True
        assert job.employment_type == EmploymentType.FULL_TIME
        assert job.description == "Build APIs"
        assert job.posted_at is not None and job.posted_at.tzinfo is not None


@pytest.mark.unit
class TestArbeitnow:
    async def test_filters_by_search_and_follows_pages(self):
        pages = {
            "1": {
                "data": [
                    {
                        "slug": "a",
                        "title": "Python Dev",
                        "company_name": "A",
                        "url": "https://x/a",
                        "remote": True,
                        "tags": [],
                        "job_types": ["Full Time"],
                        "created_at": 1760000000,
                    },
                    {
                        "slug": "b",
                        "title": "Chef",
                        "company_name": "B",
                        "url": "https://x/b",
                        "tags": [],
                    },
                ],
                "links": {"next": "page2"},
            },
            "2": {
                "data": [
                    {
                        "slug": "c",
                        "title": "Lead",
                        "company_name": "C",
                        "url": "https://x/c",
                        "tags": ["Python"],
                    }
                ],
                "links": {"next": None},
            },
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=pages[request.url.params["page"]])

        result = await ArbeitnowConnector(fetcher_for(handler)).fetch(
            {"search": "python", "max_pages": 3}, 50
        )
        assert [j.external_id for j in result.jobs] == ["a", "c"]
        assert result.jobs[0].employment_type == EmploymentType.FULL_TIME


@pytest.mark.unit
class TestRemoteOk:
    async def test_skips_the_legal_notice(self):
        payload = [
            {"legal": "Terms"},
            {
                "id": "9",
                "position": "SRE",
                "company": "Globex",
                "url": "https://remoteok.com/9",
                "salary_min": 90000,
                "salary_max": 120000,
                "epoch": 1760000000,
                "tags": ["sre"],
            },
        ]
        result = await RemoteOkConnector(fetcher_for(json_response(payload))).fetch(
            {}, 50
        )
        assert len(result.jobs) == 1
        assert result.skipped == 0
        assert (result.jobs[0].salary_min, result.jobs[0].salary_currency) == (
            90000,
            "USD",
        )


@pytest.mark.unit
class TestAdzuna:
    async def test_needs_credentials(self):
        connector = AdzunaConnector(
            fetcher_for(json_response({})), app_id="", app_key=""
        )
        with pytest.raises(ExternalServiceError, match="ADZUNA"):
            await connector.fetch({"country": "gb"}, 10)

    async def test_maps_nested_fields_and_currency(self):
        payload = {
            "results": [
                {
                    "id": "77",
                    "title": "Data Analyst (Remote)",
                    "company": {"display_name": "Initech"},
                    "location": {"display_name": "London"},
                    "redirect_url": "https://adzuna.co.uk/77",
                    "salary_min": 40000,
                    "salary_max": 50000,
                    "contract_time": "full_time",
                    "category": {"label": "IT Jobs"},
                    "created": "2026-10-10T09:00:00Z",
                }
            ]
        }
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            return httpx.Response(200, json=payload)

        connector = AdzunaConnector(fetcher_for(handler), app_id="id", app_key="key")
        result = await connector.fetch({"country": "gb", "max_pages": 2}, 10)
        assert seen["path"] == "/v1/api/jobs/gb/search/1"
        job = result.jobs[0]
        assert (job.company, job.location, job.salary_currency) == (
            "Initech",
            "London",
            "GBP",
        )
        assert job.is_remote is True
        assert job.category == "IT Jobs"


@pytest.mark.unit
class TestRssFeed:
    async def test_rss(self):
        xml = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Acme Careers</title>
          <item><title>Backend Engineer</title><link>https://acme.example/jobs/1</link>
            <guid>acme-1</guid><description>&lt;p&gt;Remote role&lt;/p&gt;</description>
            <pubDate>Mon, 06 Oct 2026 10:00:00 GMT</pubDate><category>python</category></item>
          <item><title>No link</title></item>
        </channel></rss>"""
        handler = lambda request: httpx.Response(200, content=xml)  # noqa: E731
        result = await RssFeedConnector(fetcher_for(handler)).fetch(
            {"url": "https://acme.example/feed"}, 10
        )
        assert result.skipped == 1
        job = result.jobs[0]
        assert (job.external_id, job.company, job.is_remote) == (
            "acme-1",
            "Acme Careers",
            True,
        )
        assert job.tags == ("python",)

    async def test_atom(self):
        xml = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Board</title>
          <entry><id>urn:1</id><title>Designer</title>
            <link rel="alternate" href="https://board.example/1"/>
            <summary>Craft UI</summary><published>2026-10-05T08:00:00Z</published></entry>
        </feed>"""
        handler = lambda request: httpx.Response(200, content=xml)  # noqa: E731
        result = await RssFeedConnector(fetcher_for(handler)).fetch(
            {"url": "https://board.example/atom", "company": "Board Inc"}, 10
        )
        assert result.jobs[0].url == "https://board.example/1"
        assert result.jobs[0].company == "Board Inc"

    async def test_entity_expansion_is_refused(self):
        bomb = b"""<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">
          <!ENTITY lol2 "&lol;&lol;&lol;">]><rss><channel><title>&lol2;</title></channel></rss>"""
        handler = lambda request: httpx.Response(200, content=bomb)  # noqa: E731
        with pytest.raises(ExternalServiceError):
            await RssFeedConnector(fetcher_for(handler)).fetch(
                {"url": "https://x.example/f"}, 10
            )


@pytest.mark.unit
class TestJsonFeed:
    def test_pick_follows_dicts_and_list_indexes(self):
        data = {"a": {"b": [{"c": 1}, {"c": 2}]}}
        assert pick(data, "a.b.1.c") == 2
        assert pick(data, "a.missing.c") is None
        assert pick(data, "a.b.9.c") is None

    async def test_maps_items_through_the_field_map(self):
        payload = {
            "data": {
                "jobs": [
                    {
                        "key": "j1",
                        "position": "ML Engineer",
                        "org": {"name": "Hooli"},
                        "links": {"apply": "https://hooli.example/j1"},
                        "remote": False,
                    },
                    {"key": "j2", "position": "Broken"},
                ]
            }
        }
        config = {
            "url": "https://hooli.example/jobs.json",
            "items_path": "data.jobs",
            "field_map": {
                "id": "key",
                "title": "position",
                "company": "org.name",
                "url": "links.apply",
                "remote": "remote",
            },
        }
        result = await JsonFeedConnector(fetcher_for(json_response(payload))).fetch(
            config, 10
        )
        assert [j.external_id for j in result.jobs] == ["j1"]
        assert result.jobs[0].is_remote is False
        assert result.skipped == 1

    async def test_items_path_must_point_at_a_list(self):
        config = {
            "url": "https://x.example/j",
            "items_path": "data",
            "field_map": {"title": "t", "url": "u"},
        }
        with pytest.raises(ExternalServiceError, match="list"):
            await JsonFeedConnector(fetcher_for(json_response({"data": {}}))).fetch(
                config, 10
            )

    async def test_non_json_is_an_external_error(self):
        handler = lambda request: httpx.Response(200, content=b"<html>")  # noqa: E731
        with pytest.raises(ExternalServiceError, match="JSON"):
            await JsonFeedConnector(fetcher_for(handler)).fetch(
                {"url": "https://x.example/j", "field_map": {"title": "t", "url": "u"}},
                10,
            )


def test_json_response_helper_is_valid_json():
    assert json.loads(
        json_response({"a": 1})(httpx.Request("GET", "https://x")).content
    ) == {"a": 1}
