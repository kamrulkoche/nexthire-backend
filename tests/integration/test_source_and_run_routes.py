"""Integration tests for job sources, collection runs and both dashboards."""

from datetime import UTC, datetime, timedelta

import time

import pytest
from fastapi.testclient import TestClient
from src.shared.infrastructure.database import MongoSession

from src.modules.collection.application.use_cases.run_use_cases import (
    ExecuteRunUseCase,
    StartRunUseCase,
)
from src.modules.collection.domain.enums.run_trigger import RunTrigger
from src.modules.job.domain.entities.job import Job
from src.modules.job_source.domain.enums.source_type import SourceType
from src.modules.notification.domain.entities.notification import Notification
from src.shared.domain.exceptions.external_service_error import ExternalServiceError

from .conftest import FakeConnector, collected

SOURCES = "/api/v1/admin/sources"
RUNS = "/api/v1/admin/runs"


def _create_source(client: TestClient, headers: dict, **overrides) -> dict:
    body = {
        "name": "Remotive — Python",
        "slug": "remotive-python",
        "source_type": "remotive",
        "config": {"search": "python"},
        "schedule_minutes": 60,
    }
    body.update(overrides)
    response = client.post(SOURCES, json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _run(client: TestClient, headers: dict, source_id: str) -> dict:
    started = client.post(RUNS, json={"source_id": source_id}, headers=headers)
    assert started.status_code == 202, started.text
    # The inline dispatcher has already finished the work; read the outcome.
    return client.get(f"{RUNS}/{started.json()['data']['id']}", headers=headers).json()[
        "data"
    ]


@pytest.mark.integration
class TestSources:
    def test_seekers_cannot_manage_sources(self, client: TestClient, seeker_headers):
        assert client.get(SOURCES, headers=seeker_headers).status_code == 403
        assert client.get(RUNS, headers=seeker_headers).status_code == 403

    def test_create_normalizes_the_config(self, client, admin_headers):
        data = _create_source(
            client,
            admin_headers,
            slug="Adzuna-GB",
            source_type="adzuna",
            config={"country": "GB", "what": " python "},
        )
        assert data["slug"] == "adzuna-gb"
        assert data["config"] == {"country": "gb", "what": "python", "max_pages": 1}
        assert data["active_jobs"] == 0
        assert data["is_running"] is False

    @pytest.mark.parametrize(
        "source_type, config",
        [
            ("remotive", {"serach": "typo"}),
            ("adzuna", {"what": "python"}),
            ("rss_feed", {"url": "ftp://example.com/feed"}),
            ("json_feed", {"url": "https://example.com/jobs.json"}),
            (
                "json_feed",
                {"url": "https://example.com/j", "field_map": {"title": "t"}},
            ),
        ],
    )
    def test_bad_config_is_422(self, client, admin_headers, source_type, config):
        response = client.post(
            SOURCES,
            json={
                "name": "Bad",
                "slug": "bad",
                "source_type": source_type,
                "config": config,
            },
            headers=admin_headers,
        )
        assert response.status_code == 422, response.text

    def test_slug_conflict_is_409_even_after_delete(self, client, admin_headers):
        created = _create_source(client, admin_headers)
        assert (
            client.delete(
                f"{SOURCES}/{created['id']}", headers=admin_headers
            ).status_code
            == 204
        )
        assert (
            client.get(f"{SOURCES}/{created['id']}", headers=admin_headers).status_code
            == 404
        )
        again = client.post(
            SOURCES,
            json={
                "name": "Again",
                "slug": "remotive-python",
                "source_type": "remotive",
            },
            headers=admin_headers,
        )
        assert again.status_code == 409

    def test_update_checks_config_against_the_stored_type(self, client, admin_headers):
        created = _create_source(client, admin_headers)
        bad = client.patch(
            f"{SOURCES}/{created['id']}",
            json={"config": {"country": "gb"}},
            headers=admin_headers,
        )
        assert bad.status_code == 422
        good = client.patch(
            f"{SOURCES}/{created['id']}",
            json={"config": {"category": "software-dev"}, "is_enabled": False},
            headers=admin_headers,
        )
        assert good.json()["data"]["config"] == {"category": "software-dev"}
        assert good.json()["data"]["is_enabled"] is False


@pytest.mark.integration
class TestRuns:
    def test_manual_run_stores_jobs_and_records_counts(
        self, client: TestClient, admin_headers, seeker_headers, fake_connector
    ):
        fake_connector(
            FakeConnector(
                [
                    collected("1", "Python Developer"),
                    collected("2", "Data Engineer", "Globex"),
                ],
                skipped=1,
            )
        )
        source = _create_source(client, admin_headers)
        run = _run(client, admin_headers, source["id"])

        assert run["status"] == "partial"  # one posting was skipped
        assert run["trigger"] == "manual"
        assert run["source_name"] == "Remotive — Python"
        assert (run["fetched_count"], run["created_count"], run["skipped_count"]) == (
            2,
            2,
            1,
        )
        assert run["duration_ms"] is not None

        source_after = client.get(
            f"{SOURCES}/{source['id']}", headers=admin_headers
        ).json()["data"]
        assert source_after["last_run_status"] == "partial"
        assert source_after["active_jobs"] == 2
        assert source_after["is_running"] is False
        assert (
            client.get("/api/v1/app/jobs", headers=seeker_headers).json()["data"][
                "total"
            ]
            == 2
        )

    def test_second_run_updates_rather_than_duplicates(
        self, client, admin_headers, fake_connector
    ):
        connector = fake_connector(FakeConnector([collected("1", "Python Developer")]))
        source = _create_source(client, admin_headers)
        _run(client, admin_headers, source["id"])
        connector.jobs = [
            collected("1", "Senior Python Developer"),
            collected("2", "SRE"),
        ]
        run = _run(client, admin_headers, source["id"])
        assert (run["created_count"], run["updated_count"], run["status"]) == (
            1,
            1,
            "succeeded",
        )

        titles = sorted(
            j["title"]
            for j in client.get("/api/v1/admin/jobs", headers=admin_headers).json()[
                "data"
            ]["items"]
        )
        assert titles == ["SRE", "Senior Python Developer"]

    def test_same_posting_on_two_sources_is_shown_once(
        self, client, admin_headers, seeker_headers, fake_connector
    ):
        fake_connector(
            FakeConnector([collected("r-1", "Python Developer (Remote)", "Acme Inc.")])
        )
        fake_connector(
            FakeConnector([collected("a-9", "python developer", "ACME")]),
            SourceType.ARBEITNOW,
        )
        first = _create_source(client, admin_headers)
        second = _create_source(
            client, admin_headers, slug="arbeitnow", source_type="arbeitnow", config={}
        )
        _run(client, admin_headers, first["id"])
        run = _run(client, admin_headers, second["id"])
        assert run["duplicate_count"] == 1
        assert (
            client.get("/api/v1/app/jobs", headers=seeker_headers).json()["data"][
                "total"
            ]
            == 1
        )

    def test_failed_run_is_recorded_and_admins_are_told(
        self, client, db_session: MongoSession, admin, admin_headers, fake_connector
    ):
        fake_connector(
            FakeConnector(error=ExternalServiceError("remotive", "Answered HTTP 503."))
        )
        source = _create_source(client, admin_headers)
        run = _run(client, admin_headers, source["id"])
        assert run["status"] == "failed"
        assert "503" in run["error_message"]

        source_after = client.get(
            f"{SOURCES}/{source['id']}", headers=admin_headers
        ).json()["data"]
        assert source_after["is_running"] is False  # the claim was released
        assert source_after["next_run_at"] is not None  # backs off a full interval

        notes = db_session.load_many(
            Notification,
            db_session.collection(Notification).find({"user_id": admin.id}),
        )
        assert [n.kind.value for n in notes] == ["run_failed"]
        assert notes[0].link == "/admin/runs"

    async def test_a_claimed_source_cannot_be_run_twice(
        self, client, db_session: MongoSession, admin_headers, make_source
    ):
        source = make_source()
        await StartRunUseCase(db_session).execute(
            source.id, trigger=RunTrigger.SCHEDULED
        )
        response = client.post(
            RUNS, json={"source_id": str(source.id)}, headers=admin_headers
        )
        assert response.status_code == 409

    async def test_jobs_the_source_stopped_listing_go_stale(
        self, db_session: MongoSession, make_source, make_job, fake_connector
    ):
        source = make_source()
        old = datetime.now(UTC) - timedelta(days=45)
        stale = make_job("Old Role", source_id=source.id, last_seen_at=old)
        fake_connector(FakeConnector([collected("fresh", "New Role")]))

        run = await StartRunUseCase(db_session).execute(
            source.id, trigger=RunTrigger.SCHEDULED
        )
        run = await ExecuteRunUseCase(db_session).execute(run.id)
        assert run.deactivated_count == 1
        db_session.refresh(stale)
        assert stale.is_active is False

    def test_new_jobs_are_matched_and_seekers_notified(
        self,
        client,
        db_session: MongoSession,
        admin_headers,
        seeker,
        seeker_headers,
        fake_connector,
    ):
        client.put(
            "/api/v1/app/preferences",
            json={"keywords": ["python", "fastapi"], "notify_on_match": True},
            headers=seeker_headers,
        )
        fake_connector(
            FakeConnector(
                [
                    collected(
                        "1", "Python FastAPI Engineer", tags=("python", "fastapi")
                    ),
                    collected("2", "Accountant", description="Spreadsheets."),
                ]
            )
        )
        source = _create_source(client, admin_headers)
        _run(client, admin_headers, source["id"])

        recs = client.get("/api/v1/app/recommendations", headers=seeker_headers).json()[
            "data"
        ]
        assert [r["job"]["title"] for r in recs["items"]] == ["Python FastAPI Engineer"]
        count = client.get(
            "/api/v1/app/notifications/unread-count", headers=seeker_headers
        )
        assert count.json()["data"]["unread"] == 1
        note = client.get("/api/v1/app/notifications", headers=seeker_headers).json()[
            "data"
        ]["items"][0]
        assert note["kind"] == "new_matches"
        assert note["link"] == "/app/recommendations"

    def test_history_filters(self, client, admin_headers, fake_connector):
        connector = fake_connector(FakeConnector([collected("1", "Role")]))
        source = _create_source(client, admin_headers)
        _run(client, admin_headers, source["id"])
        # MongoDB keeps milliseconds; two inline runs can start in the same
        # one, and then "newest first" has no order to go by.
        time.sleep(0.005)
        connector.error = ExternalServiceError("remotive", "Down.")
        _run(client, admin_headers, source["id"])

        all_runs = client.get(RUNS, headers=admin_headers).json()["data"]
        assert all_runs["total"] == 2
        assert all_runs["items"][0]["status"] == "failed"  # newest first
        failed = client.get(
            RUNS, params={"status": "failed"}, headers=admin_headers
        ).json()["data"]
        assert failed["total"] == 1


@pytest.mark.integration
class TestDashboards:
    def test_seeker_dashboard(self, client, seeker_headers, make_job):
        job = make_job()
        client.put(f"/api/v1/app/saved-jobs/{job.id}", json={}, headers=seeker_headers)
        client.post(
            "/api/v1/app/applications",
            json={"title": "Role", "company": "Co", "status": "applied"},
            headers=seeker_headers,
        )
        data = client.get("/api/v1/app/dashboard", headers=seeker_headers).json()[
            "data"
        ]
        assert data["saved_jobs"] == 1
        assert data["applications"]["applied"] == 1
        assert data["has_preferences"] is False
        assert data["new_jobs_this_week"] == 1
        assert data["unavailable"] == []

    def test_admin_dashboard(
        self, client, admin_headers, seeker, fake_connector, db_session
    ):
        fake_connector(FakeConnector([collected("1", "Role")]))
        source = _create_source(client, admin_headers)
        _run(client, admin_headers, source["id"])
        data = client.get("/api/v1/admin/dashboard", headers=admin_headers).json()[
            "data"
        ]
        assert data["jobs"]["visible"] == 1
        assert (data["sources_total"], data["sources_enabled"]) == (1, 1)
        assert data["runs_last_24h"] == {"succeeded": 1}
        assert (data["seekers"], data["admins"]) == (1, 1)
        assert len(data["recent_runs"]) == 1
        assert data["unavailable"] == []
        assert db_session.collection(Job).find_one({}) is not None

    def test_seekers_cannot_read_the_admin_dashboard(self, client, seeker_headers):
        assert (
            client.get("/api/v1/admin/dashboard", headers=seeker_headers).status_code
            == 403
        )


@pytest.mark.integration
def test_a_bad_setting_is_reported_under_config(client: TestClient, admin_headers):
    response = client.post(
        SOURCES,
        json={
            "name": "Bad",
            "slug": "bad",
            "source_type": "adzuna",
            "config": {"what": "x"},
        },
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert response.json()["details"]["fields"] == {"config": "'country' is required"}
