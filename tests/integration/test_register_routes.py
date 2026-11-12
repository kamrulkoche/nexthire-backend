"""Integration tests for self-registration."""

import pytest
from fastapi.testclient import TestClient

REGISTER = "/api/v1/auth/register"
PASSWORD = "a-long-enough-password"


@pytest.mark.integration
class TestRegister:
    def test_creates_a_signed_in_seeker(self, client: TestClient):
        response = client.post(
            REGISTER,
            json={
                "name": "Rina Das",
                "email": "Rina@Example.com",
                "password": PASSWORD,
            },
        )
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["user"]["role"] == "seeker"
        assert data["user"]["email"] == "rina@example.com"
        assert "password_hash" not in data["user"]
        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
        assert me.status_code == 200

    def test_a_role_in_the_body_is_ignored(self, client: TestClient):
        response = client.post(
            REGISTER,
            json={
                "name": "Mallory",
                "email": "m@example.com",
                "password": PASSWORD,
                "role": "admin",
            },
        )
        assert response.json()["data"]["user"]["role"] == "seeker"

    def test_duplicate_email_is_409(self, client: TestClient, seeker):
        response = client.post(
            REGISTER,
            json={"name": "Again", "email": seeker.email.upper(), "password": PASSWORD},
        )
        assert response.status_code == 409

    def test_short_password_is_422(self, client: TestClient):
        response = client.post(
            REGISTER,
            json={"name": "Short", "email": "s@example.com", "password": "short"},
        )
        assert response.status_code == 422
        assert "password" in response.json()["details"]["fields"]

    def test_sixth_registration_from_one_address_is_rate_limited(
        self, client: TestClient
    ):
        for i in range(5):
            client.post(
                REGISTER,
                json={
                    "name": f"User {i}",
                    "email": f"u{i}@example.com",
                    "password": PASSWORD,
                },
            )
        response = client.post(
            REGISTER,
            json={"name": "User 6", "email": "u6@example.com", "password": PASSWORD},
        )
        assert response.status_code == 429
