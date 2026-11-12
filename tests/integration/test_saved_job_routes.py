"""Integration tests for saved jobs."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

SAVED = "/api/v1/app/saved-jobs"


@pytest.mark.integration
class TestSavedJobs:
    def test_save_is_idempotent_and_updates_the_note(
        self, client: TestClient, seeker_headers, make_job
    ):
        job = make_job()
        first = client.put(
            f"{SAVED}/{job.id}", json={"note": "Apply Monday"}, headers=seeker_headers
        )
        assert first.status_code == 200
        assert first.json()["data"]["job"]["is_saved"] is True
        second = client.put(
            f"{SAVED}/{job.id}", json={"note": "Applied"}, headers=seeker_headers
        )
        assert second.json()["data"]["note"] == "Applied"

        listed = client.get(SAVED, headers=seeker_headers).json()["data"]
        assert listed["total"] == 1
        assert listed["items"][0]["note"] == "Applied"

    def test_unknown_or_hidden_job_is_a_404(self, client, seeker_headers, make_job):
        hidden = make_job(is_hidden=True)
        assert (
            client.put(
                f"{SAVED}/{uuid4()}", json={}, headers=seeker_headers
            ).status_code
            == 404
        )
        assert (
            client.put(
                f"{SAVED}/{hidden.id}", json={}, headers=seeker_headers
            ).status_code
            == 404
        )

    def test_a_saved_job_that_goes_away_stays_listed(
        self, client, seeker_headers, admin_headers, make_job
    ):
        job = make_job()
        client.put(f"{SAVED}/{job.id}", json={}, headers=seeker_headers)
        client.patch(
            f"/api/v1/admin/jobs/{job.id}",
            json={"is_hidden": True},
            headers=admin_headers,
        )
        items = client.get(SAVED, headers=seeker_headers).json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["job"]["is_available"] is False

    def test_bookmarks_are_private(
        self, client, seeker_headers, other_seeker_headers, make_job
    ):
        job = make_job()
        client.put(f"{SAVED}/{job.id}", json={}, headers=seeker_headers)
        assert (
            client.get(SAVED, headers=other_seeker_headers).json()["data"]["total"] == 0
        )
        # Another seeker cannot remove it either: from their side it does not exist.
        assert (
            client.delete(f"{SAVED}/{job.id}", headers=other_seeker_headers).status_code
            == 404
        )
        assert client.get(SAVED, headers=seeker_headers).json()["data"]["total"] == 1

    def test_unsave(self, client, seeker_headers, make_job):
        job = make_job()
        client.put(f"{SAVED}/{job.id}", json={}, headers=seeker_headers)
        assert (
            client.delete(f"{SAVED}/{job.id}", headers=seeker_headers).status_code
            == 204
        )
        assert (
            client.delete(f"{SAVED}/{job.id}", headers=seeker_headers).status_code
            == 404
        )
