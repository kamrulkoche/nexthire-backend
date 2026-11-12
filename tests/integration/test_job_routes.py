"""Integration tests for Job Search, Job Details, moderation and public stats."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.modules.job.domain.enums.employment_type import EmploymentType

JOBS = "/api/v1/app/jobs"
ADMIN_JOBS = "/api/v1/admin/jobs"


@pytest.mark.integration
class TestJobSearch:
    def test_requires_a_session(self, client: TestClient):
        assert client.get(JOBS).status_code == 401

    def test_lists_only_visible_jobs(
        self, client: TestClient, seeker_headers, make_job
    ):
        visible = make_job("Python Developer")
        make_job("Hidden Role", is_hidden=True)
        make_job("Stale Role", is_active=False)
        make_job("Copy Of Python Developer", duplicate_of_id=visible.id)

        data = client.get(JOBS, headers=seeker_headers).json()["data"]
        assert [j["title"] for j in data["items"]] == ["Python Developer"]
        assert data["total"] == 1

    def test_every_search_word_must_match(
        self, client: TestClient, seeker_headers, make_job
    ):
        make_job("Senior Python Engineer", description="Django and AWS.")
        make_job("Python Data Analyst", description="SQL and pandas.")
        data = client.get(
            JOBS, params={"search": "python django"}, headers=seeker_headers
        ).json()["data"]
        assert [j["title"] for j in data["items"]] == ["Senior Python Engineer"]

    def test_filters(self, client: TestClient, seeker_headers, make_job):
        old = datetime.now(UTC) - timedelta(days=40)
        make_job(
            "Remote Contract", is_remote=True, employment_type=EmploymentType.CONTRACT
        )
        make_job("Onsite Rich", salary_min=90000, salary_max=120000)
        make_job("Onsite Old", posted_at=old, first_seen_at=old)

        def titles(**params):
            body = client.get(JOBS, params=params, headers=seeker_headers).json()
            return sorted(j["title"] for j in body["data"]["items"])

        assert titles(remote="true") == ["Remote Contract"]
        assert titles(employment_type="contract") == ["Remote Contract"]
        assert titles(salary_min=100000) == ["Onsite Rich"]
        assert "Onsite Old" not in titles(posted_within_days=7)

    def test_newest_first_by_default(
        self, client: TestClient, seeker_headers, make_job
    ):
        now = datetime.now(UTC)
        make_job("Older", posted_at=now - timedelta(days=3))
        make_job("Newer", posted_at=now - timedelta(hours=1))
        items = client.get(JOBS, headers=seeker_headers).json()["data"]["items"]
        assert [j["title"] for j in items] == ["Newer", "Older"]

    def test_cards_carry_the_callers_saved_flag(
        self, client: TestClient, seeker_headers, other_seeker_headers, make_job
    ):
        job = make_job()
        client.put(f"/api/v1/app/saved-jobs/{job.id}", json={}, headers=seeker_headers)
        mine = client.get(JOBS, headers=seeker_headers).json()["data"]["items"][0]
        theirs = client.get(JOBS, headers=other_seeker_headers).json()["data"]["items"][
            0
        ]
        assert mine["is_saved"] is True
        assert theirs["is_saved"] is False
        assert mine["source_name"] == "Fixture Source"

    def test_unknown_sort_falls_back_rather_than_erroring(
        self, client: TestClient, seeker_headers, make_job
    ):
        make_job()
        response = client.get(
            JOBS, params={"sort": "is_hidden"}, headers=seeker_headers
        )
        assert response.status_code == 200


@pytest.mark.integration
class TestJobDetail:
    def test_returns_description_and_apply_url(self, client, seeker_headers, make_job):
        job = make_job()
        data = client.get(f"{JOBS}/{job.id}", headers=seeker_headers).json()["data"]
        assert data["url"] == job.url
        assert "FastAPI" in data["description"]
        # Moderation fields never reach a seeker.
        assert "is_hidden" not in data and "external_id" not in data

    def test_hidden_job_is_a_404(self, client, seeker_headers, make_job):
        job = make_job(is_hidden=True)
        assert client.get(f"{JOBS}/{job.id}", headers=seeker_headers).status_code == 404


@pytest.mark.integration
class TestModeration:
    def test_seekers_cannot_moderate(self, client, seeker_headers, make_job):
        job = make_job()
        assert client.get(ADMIN_JOBS, headers=seeker_headers).status_code == 403
        response = client.patch(
            f"{ADMIN_JOBS}/{job.id}", json={"is_hidden": True}, headers=seeker_headers
        )
        assert response.status_code == 403

    def test_admin_hides_a_job_and_it_leaves_search(
        self, client, admin_headers, seeker_headers, make_job
    ):
        job = make_job()
        response = client.patch(
            f"{ADMIN_JOBS}/{job.id}", json={"is_hidden": True}, headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["data"]["is_hidden"] is True
        assert client.get(JOBS, headers=seeker_headers).json()["data"]["total"] == 0

        listed = client.get(
            ADMIN_JOBS, params={"hidden": "true"}, headers=admin_headers
        ).json()["data"]
        assert [j["id"] for j in listed["items"]] == [str(job.id)]


@pytest.mark.integration
class TestPublicStats:
    def test_counts_without_a_session(self, client, make_job, make_source):
        make_job("A", company="Acme")
        make_job("B", company="Globex")
        make_job("C", company="Globex", is_hidden=True)
        data = client.get("/api/v1/public/stats").json()["data"]
        assert data["jobs"] == 2
        assert data["companies"] == 2
        assert data["sources"] == 1
        assert data["new_this_week"] == 2
