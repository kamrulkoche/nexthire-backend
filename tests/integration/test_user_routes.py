"""Integration tests for admin user management."""

import pytest
from fastapi.testclient import TestClient

from src.modules.user.domain.entities.user import User

from .conftest import login

USERS = "/api/v1/admin/users"


@pytest.mark.integration
class TestUsers:
    def test_seekers_cannot_manage_users(
        self, client: TestClient, seeker_headers: dict
    ):
        assert client.get(USERS, headers=seeker_headers).status_code == 403
        assert client.post(USERS, json={}, headers=seeker_headers).status_code == 403

    def test_admin_creates_an_seeker_who_can_then_sign_in(
        self, client: TestClient, admin_headers: dict
    ):
        response = client.post(
            USERS,
            json={
                "name": "New Seeker",
                "email": "New.Seeker@nexthire.dev",
                "role": "seeker",
                "password": "a-long-enough-password",
            },
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        created = response.json()["data"]
        assert created["email"] == "new.seeker@nexthire.dev"
        assert "password" not in created and "password_hash" not in created

        signed_in = client.post(
            "/api/v1/auth/login",
            json={
                "email": "new.seeker@nexthire.dev",
                "password": "a-long-enough-password",
            },
        )
        assert signed_in.status_code == 200

    def test_duplicate_email_is_409(
        self, client: TestClient, admin_headers: dict, seeker: User
    ):
        response = client.post(
            USERS,
            json={
                "name": "Dup",
                "email": seeker.email,
                "password": "a-long-enough-password",
            },
            headers=admin_headers,
        )
        assert response.status_code == 409

    def test_short_password_is_422(self, client: TestClient, admin_headers: dict):
        response = client.post(
            USERS,
            json={"name": "Weak", "email": "weak@nexthire.dev", "password": "short"},
            headers=admin_headers,
        )
        assert response.status_code == 422
        assert "password" in response.json()["details"]["fields"]

    def test_role_filter_and_search(
        self, client: TestClient, admin_headers: dict, seeker: User, other_seeker: User
    ):
        seekers = client.get(
            USERS, params={"role": "seeker"}, headers=admin_headers
        ).json()["data"]
        assert seekers["total"] == 2
        found = client.get(
            USERS, params={"search": "daniel"}, headers=admin_headers
        ).json()["data"]
        assert [u["email"] for u in found["items"]] == [other_seeker.email]

    def test_last_admin_cannot_demote_themselves(
        self, client: TestClient, admin: User, admin_headers: dict
    ):
        response = client.patch(
            f"{USERS}/{admin.id}", json={"role": "seeker"}, headers=admin_headers
        )
        assert response.status_code == 422

    def test_deactivating_an_seeker_ends_their_session(
        self,
        client: TestClient,
        admin_headers: dict,
        seeker: User,
        seeker_headers: dict,
    ):
        response = client.patch(
            f"{USERS}/{seeker.id}", json={"status": "inactive"}, headers=admin_headers
        )
        assert response.status_code == 200
        assert client.get("/api/v1/auth/me", headers=seeker_headers).status_code == 401

    def test_promotion_invalidates_the_old_token_claim(
        self,
        client: TestClient,
        admin_headers: dict,
        seeker: User,
        seeker_headers: dict,
    ):
        client.patch(
            f"{USERS}/{seeker.id}", json={"role": "admin"}, headers=admin_headers
        )
        # The old token says "seeker"; the database now says "admin". The
        # mismatch forces a fresh sign-in rather than trusting either.
        assert client.get("/api/v1/auth/me", headers=seeker_headers).status_code == 401
        assert client.get(USERS, headers=login(client, seeker)).status_code == 200
