"""Integration tests for the application tracker."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

APPS = "/api/v1/app/applications"


@pytest.mark.integration
class TestTracker:
    def test_tracking_a_job_snapshots_its_details(
        self, client: TestClient, seeker_headers, make_job
    ):
        job = make_job("Backend Engineer", company="Initech", location="Remote")
        response = client.post(
            APPS, json={"job_id": str(job.id)}, headers=seeker_headers
        )
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["title"] == "Backend Engineer"
        assert data["company"] == "Initech"
        assert data["url"] == job.url
        assert data["status"] == "interested"
        assert data["job_available"] is True

    def test_one_row_per_job(self, client, seeker_headers, make_job):
        job = make_job()
        client.post(APPS, json={"job_id": str(job.id)}, headers=seeker_headers)
        again = client.post(APPS, json={"job_id": str(job.id)}, headers=seeker_headers)
        assert again.status_code == 409

    def test_a_job_found_elsewhere_can_be_tracked_by_hand(self, client, seeker_headers):
        response = client.post(
            APPS,
            json={
                "title": "Data Engineer",
                "company": "Hooli",
                "url": "",
                "status": "applied",
            },
            headers=seeker_headers,
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["job_id"] is None
        assert data["url"] is None
        # The server fills in the UTC date; the frontend sends the local one.
        assert data["applied_on"] == datetime.now(UTC).date().isoformat()

    def test_needs_a_job_or_details(self, client, seeker_headers):
        assert (
            client.post(
                APPS, json={"title": "Only a title"}, headers=seeker_headers
            ).status_code
            == 422
        )

    def test_moving_to_applied_fills_the_date_and_counts_follow(
        self, client, seeker_headers, make_job
    ):
        created = client.post(
            APPS, json={"job_id": str(make_job().id)}, headers=seeker_headers
        ).json()["data"]
        updated = client.patch(
            f"{APPS}/{created['id']}",
            json={"status": "applied"},
            headers=seeker_headers,
        ).json()["data"]
        assert updated["status"] == "applied"
        assert updated["applied_on"] is not None
        assert updated["status_changed_at"] is not None

        counts = client.get(f"{APPS}/counts", headers=seeker_headers).json()["data"]
        assert counts["applied"] == 1
        assert counts["total"] == 1

    def test_status_filter_and_search(self, client, seeker_headers):
        for title, company, status in [
            ("Platform Engineer", "Umbrella", "interviewing"),
            ("QA Lead", "Umbrella", "rejected"),
            ("SRE", "Wayne", "interviewing"),
        ]:
            client.post(
                APPS,
                json={"title": title, "company": company, "status": status},
                headers=seeker_headers,
            )
        interviewing = client.get(
            APPS, params={"status": "interviewing"}, headers=seeker_headers
        )
        assert interviewing.json()["data"]["total"] == 2
        found = client.get(APPS, params={"search": "umbrella"}, headers=seeker_headers)
        assert found.json()["data"]["total"] == 2

    def test_rows_are_private(self, client, seeker_headers, other_seeker_headers):
        row = client.post(
            APPS, json={"title": "Mine", "company": "Me"}, headers=seeker_headers
        ).json()["data"]
        assert (
            client.get(f"{APPS}/{row['id']}", headers=other_seeker_headers).status_code
            == 404
        )
        response = client.patch(
            f"{APPS}/{row['id']}",
            json={"status": "hired"},
            headers=other_seeker_headers,
        )
        assert response.status_code == 404
        assert (
            client.get(APPS, headers=other_seeker_headers).json()["data"]["total"] == 0
        )

    def test_delete_is_soft_and_frees_the_job(self, client, seeker_headers, make_job):
        job = make_job()
        row = client.post(
            APPS, json={"job_id": str(job.id)}, headers=seeker_headers
        ).json()["data"]
        assert (
            client.delete(f"{APPS}/{row['id']}", headers=seeker_headers).status_code
            == 204
        )
        assert (
            client.get(f"{APPS}/{row['id']}", headers=seeker_headers).status_code == 404
        )
        # The job can be tracked again after the row is removed.
        again = client.post(APPS, json={"job_id": str(job.id)}, headers=seeker_headers)
        assert again.status_code == 201
