"""Integration tests for preferences and AI recommendations."""

from typing import Sequence

import pytest
from fastapi.testclient import TestClient

from src.modules.recommendation.api.dependencies import get_job_scorer
from src.modules.recommendation.domain.services.job_scorer import (
    JobSnapshot,
    ScoredJob,
    SeekerProfile,
)
from src.shared.domain.exceptions.external_service_error import ExternalServiceError

PREFS = "/api/v1/app/preferences"
RECS = "/api/v1/app/recommendations"

PYTHON_PREFS = {
    "keywords": ["python", "fastapi", " Python "],
    "excluded_keywords": ["php"],
    "locations": [],
    "remote_only": False,
    "employment_types": ["full_time"],
    "profile_summary": "Backend developer, five years of Python.",
}


class FakeAIScorer:
    """Pretends to be Gemini: scores everything 88."""

    name = "gemini-test-model"

    async def score(self, profile: SeekerProfile, jobs: Sequence[JobSnapshot]):
        return [ScoredJob(job_id=j.id, score=88, rationale="Strong fit.") for j in jobs]


class BrokenAIScorer:
    """Pretends Gemini is down."""

    name = "gemini-test-model"

    async def score(self, profile: SeekerProfile, jobs: Sequence[JobSnapshot]):
        raise ExternalServiceError("gemini", "Answered HTTP 503.")


@pytest.mark.integration
class TestPreferences:
    def test_defaults_before_the_first_save(self, client: TestClient, seeker_headers):
        data = client.get(PREFS, headers=seeker_headers).json()["data"]
        assert data["exists"] is False
        assert data["keywords"] == []

    def test_put_normalizes_lists(self, client, seeker_headers):
        response = client.put(PREFS, json=PYTHON_PREFS, headers=seeker_headers)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["exists"] is True
        assert data["keywords"] == ["python", "fastapi"]

    def test_too_many_keywords_is_422(self, client, seeker_headers):
        body = {**PYTHON_PREFS, "keywords": [f"k{i}" for i in range(21)]}
        assert client.put(PREFS, json=body, headers=seeker_headers).status_code == 422

    def test_preferences_are_per_user(
        self, client, seeker_headers, other_seeker_headers
    ):
        client.put(PREFS, json=PYTHON_PREFS, headers=seeker_headers)
        assert (
            client.get(PREFS, headers=other_seeker_headers).json()["data"]["exists"]
            is False
        )


@pytest.mark.integration
class TestRecommendations:
    def test_refresh_needs_preferences(self, client, seeker_headers):
        response = client.post(f"{RECS}/refresh", headers=seeker_headers)
        assert response.status_code == 422

    def test_heuristic_refresh_scores_and_lists_best_first(
        self, client, seeker_headers, make_job
    ):
        strong = make_job("Python FastAPI Engineer", tags=["python", "fastapi"])
        make_job("Python Analyst", tags=["python"], description="Reporting in Excel.")
        make_job("PHP Developer", tags=["php"], description="Python welcome too.")
        make_job("Java Developer", tags=["java"], description="Spring Boot.")
        client.put(PREFS, json=PYTHON_PREFS, headers=seeker_headers)

        result = client.post(f"{RECS}/refresh", headers=seeker_headers).json()["data"]
        assert result["scorer"] == "heuristic"
        # Java mentions no keyword; PHP is excluded by title.
        assert result["scored"] == 2

        items = client.get(RECS, headers=seeker_headers).json()["data"]["items"]
        assert items[0]["job"]["id"] == str(strong.id)
        assert items[0]["score"] > items[1]["score"]
        assert items[0]["is_ai"] is False
        assert "python" in items[0]["matched_skills"]

        # A second refresh has nothing new to score.
        again = client.post(f"{RECS}/refresh", headers=seeker_headers).json()["data"]
        assert again["scored"] == 0

    def test_scores_show_on_search_cards(self, client, seeker_headers, make_job):
        job = make_job("Python FastAPI Engineer")
        client.put(PREFS, json=PYTHON_PREFS, headers=seeker_headers)
        client.post(f"{RECS}/refresh", headers=seeker_headers)
        card = client.get("/api/v1/app/jobs", headers=seeker_headers).json()["data"][
            "items"
        ][0]
        assert card["id"] == str(job.id)
        assert isinstance(card["match_score"], int)

    def test_ai_scorer_is_labelled(self, client, seeker_headers, make_job):
        client.app.dependency_overrides[get_job_scorer] = FakeAIScorer
        make_job("Python Engineer")
        client.put(PREFS, json=PYTHON_PREFS, headers=seeker_headers)
        result = client.post(f"{RECS}/refresh", headers=seeker_headers).json()["data"]
        assert result["scorer"] == "gemini-test-model"
        item = client.get(RECS, headers=seeker_headers).json()["data"]["items"][0]
        assert item["score"] == 88
        assert item["is_ai"] is True

    def test_ai_failure_falls_back_to_the_heuristic(
        self, client, seeker_headers, make_job
    ):
        client.app.dependency_overrides[get_job_scorer] = BrokenAIScorer
        make_job("Python Engineer")
        client.put(PREFS, json=PYTHON_PREFS, headers=seeker_headers)
        response = client.post(f"{RECS}/refresh", headers=seeker_headers)
        assert response.status_code == 200
        result = response.json()["data"]
        assert result["scored"] == 1
        assert result["scorer"] == "heuristic"
        assert result["fallback_reason"]

    def test_dismiss_hides_and_restores(self, client, seeker_headers, make_job):
        job = make_job("Python Engineer")
        client.put(PREFS, json=PYTHON_PREFS, headers=seeker_headers)
        client.post(f"{RECS}/refresh", headers=seeker_headers)
        url = f"{RECS}/{job.id}/dismiss"
        assert (
            client.put(
                url, json={"dismissed": True}, headers=seeker_headers
            ).status_code
            == 204
        )
        assert client.get(RECS, headers=seeker_headers).json()["data"]["total"] == 0
        client.put(url, json={"dismissed": False}, headers=seeker_headers)
        assert client.get(RECS, headers=seeker_headers).json()["data"]["total"] == 1

    def test_changing_preferences_clears_undismissed_matches(
        self, client, seeker_headers, make_job
    ):
        kept = make_job("Python Engineer")
        make_job("Python FastAPI Engineer")
        client.put(PREFS, json=PYTHON_PREFS, headers=seeker_headers)
        client.post(f"{RECS}/refresh", headers=seeker_headers)
        client.put(
            f"{RECS}/{kept.id}/dismiss",
            json={"dismissed": True},
            headers=seeker_headers,
        )

        client.put(
            PREFS, json={**PYTHON_PREFS, "keywords": ["python"]}, headers=seeker_headers
        )
        assert client.get(RECS, headers=seeker_headers).json()["data"]["total"] == 0
        # The dismissed one is remembered, so a refresh does not bring it back.
        client.post(f"{RECS}/refresh", headers=seeker_headers)
        ids = [
            i["job"]["id"]
            for i in client.get(RECS, headers=seeker_headers).json()["data"]["items"]
        ]
        assert str(kept.id) not in ids
        assert len(ids) == 1

    def test_matches_are_private(
        self, client, seeker_headers, other_seeker_headers, make_job
    ):
        job = make_job("Python Engineer")
        client.put(PREFS, json=PYTHON_PREFS, headers=seeker_headers)
        client.post(f"{RECS}/refresh", headers=seeker_headers)
        assert (
            client.get(RECS, headers=other_seeker_headers).json()["data"]["total"] == 0
        )
        response = client.put(
            f"{RECS}/{job.id}/dismiss",
            json={"dismissed": True},
            headers=other_seeker_headers,
        )
        assert response.status_code == 404
