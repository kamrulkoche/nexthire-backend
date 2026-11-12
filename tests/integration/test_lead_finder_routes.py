"""Lead Finder, end to end over HTTP: role isolation, registration, searches,
filters, saved leads, notes, exports, quota and the content purge.

Google is replaced by ``FakePlaces``; the task dispatcher runs inline, so a
search has finished by the time ``POST /lead/searches`` returns.
"""

import asyncio
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from src.shared.infrastructure.database import MongoSession

from src.modules.lead_finder.application.use_cases.search_use_cases import (
    SearchMaintenanceUseCase,
)
from src.modules.lead_finder.domain.entities import BusinessLead, LeadFinderSettings
from src.modules.lead_finder.infrastructure.external.google_places_client import (
    PlacesApiError,
)
from src.modules.user.domain.entities.user import User
from src.shared.domain.time import utc_now

from .conftest import TEST_PASSWORD, FakePlaces, place

SAVAR = {"division": "dhaka", "district": "dhaka", "upazila": "savar"}


def data(response: Any) -> Any:
    """The envelope's payload."""
    return response.json()["data"]


def hospitals(fake: FakePlaces) -> None:
    """Two pages: a potential lead, a business with a website, one with no
    phone, and two sharing a number (one written nationally, one
    internationally). ``p1`` appears on both pages and must be stored once."""
    fake.default_pages = [
        [
            place("p1", "Ashulia General Hospital", phone_display="01712-345678"),
            place(
                "p2",
                "City Care Hospital",
                phone_display="02-55012345",
                website_uri="https://citycare.example",
                rating=4.6,
                review_count=310,
            ),
            place("p3", "Savar Clinic", rating=3.9, review_count=12),
        ],
        [
            place("p1", "Ashulia General Hospital", phone_display="01712-345678"),
            place(
                "p4",
                "Ashulia Diagnostic",
                phone_international="+880 1712-345678",
                rating=4.1,
                review_count=40,
            ),
        ],
    ]


def run_search(client: TestClient, headers: dict, **body: Any) -> dict:
    payload = {"keyword": "Hospital", "category": "hospital", "locations": [SAVAR]}
    payload.update(body)
    response = client.post("/api/v1/lead/searches", json=payload, headers=headers)
    assert response.status_code == 202, response.text
    search_id = data(response)["id"]
    return data(client.get(f"/api/v1/lead/searches/{search_id}", headers=headers))


# ------------------------------------------------------------ authentication


def test_lead_finder_signs_in_only_through_its_own_portal(
    client: TestClient, lead_finder: User, seeker: User
) -> None:
    lead = client.post(
        "/api/v1/auth/lead-finder/login",
        json={"email": lead_finder.email, "password": TEST_PASSWORD},
    )
    assert lead.status_code == 200
    assert data(lead)["user"]["role"] == "lead_finder"

    main = client.post(
        "/api/v1/auth/login",
        json={"email": lead_finder.email, "password": TEST_PASSWORD},
    )
    assert main.status_code == 401
    assert "Lead Finder" in main.json()["error"]

    seeker_at_lead = client.post(
        "/api/v1/auth/lead-finder/login",
        json={"email": seeker.email, "password": TEST_PASSWORD},
    )
    assert seeker_at_lead.status_code == 401


def test_wrong_password_message_does_not_reveal_the_portal(
    client: TestClient, lead_finder: User
) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": lead_finder.email, "password": "wrong-one"}
    )
    assert response.status_code == 401
    assert "Lead Finder" not in response.json()["error"]


def test_roles_cannot_cross_into_each_others_dashboards(
    client: TestClient,
    lead_headers: dict,
    seeker_headers: dict,
    admin_headers: dict,
) -> None:
    for path in ("/api/v1/app/dashboard", "/api/v1/app/jobs", "/api/v1/admin/users"):
        assert client.get(path, headers=lead_headers).status_code == 403, path
    for headers in (seeker_headers, admin_headers):
        assert client.get("/api/v1/lead/overview", headers=headers).status_code == 403
        assert client.get("/api/v1/lead/leads", headers=headers).status_code == 403
    assert client.get("/api/v1/lead/overview").status_code == 401


def test_registration_is_closed_until_an_admin_opens_it(
    client: TestClient, admin_headers: dict
) -> None:
    body = {
        "name": "Tania Akter",
        "email": "tania@leads.dev",
        "password": "a-long-enough-password",
        "role": "admin",
    }
    assert (
        data(client.get("/api/v1/auth/lead-finder/status"))["registration_enabled"]
        is False
    )
    assert (
        client.post("/api/v1/auth/lead-finder/register", json=body).status_code == 403
    )

    opened = client.patch(
        "/api/v1/admin/lead-finder/settings",
        json={"registration_enabled": True},
        headers=admin_headers,
    )
    assert opened.status_code == 200
    assert data(opened)["registration_enabled"] is True

    created = client.post("/api/v1/auth/lead-finder/register", json=body)
    assert created.status_code == 201
    # The injected role is ignored.
    assert data(created)["user"]["role"] == "lead_finder"


def test_admin_manages_lead_finder_accounts_on_the_users_screen(
    client: TestClient, admin_headers: dict
) -> None:
    created = client.post(
        "/api/v1/admin/users",
        json={
            "name": "Sakib Hasan",
            "email": "sakib@leads.dev",
            "role": "lead_finder",
            "password": "a-long-enough-password",
        },
        headers=admin_headers,
    )
    assert created.status_code == 201
    listed = client.get("/api/v1/admin/users?role=lead_finder", headers=admin_headers)
    assert [u["email"] for u in data(listed)["items"]] == ["sakib@leads.dev"]


# ------------------------------------------------------------------ catalog


def test_catalog_lists_every_division_and_district(
    client: TestClient, lead_headers: dict, fake_places: FakePlaces
) -> None:
    catalog = data(client.get("/api/v1/lead/catalog", headers=lead_headers))
    assert len(catalog["divisions"]) == 8
    assert sum(len(d["districts"]) for d in catalog["divisions"]) == 64
    assert catalog["places_configured"] is True
    assert any(c["key"] == "hospital" for c in catalog["categories"])


# ------------------------------------------------------------------ search


def test_search_stores_deduplicates_and_finds_potential_leads(
    client: TestClient,
    lead_headers: dict,
    fake_places: FakePlaces,
    db_session: MongoSession,
) -> None:
    hospitals(fake_places)
    search = run_search(client, lead_headers)

    assert search["status"] == "completed"
    assert search["progress_percent"] == 100
    assert search["total_results"] == 4  # p1 found twice, stored once
    assert search["leads_found"] == 2  # p1 and p4: phone, no website
    assert search["with_phone"] == 3
    assert search["without_website"] == 3
    assert search["api_requests"] == 2
    assert fake_places.queries[0] == "Hospital in Savar, Dhaka, Bangladesh"
    assert db_session.collection(BusinessLead).count_documents({}) == 4

    leads = data(
        client.get(
            f"/api/v1/lead/leads?search_id={search['id']}&page_size=50",
            headers=lead_headers,
        )
    )["items"]
    by_place = {lead["place_id"]: lead for lead in leads}
    # Potential leads come first by default.
    assert {leads[0]["place_id"], leads[1]["place_id"]} == {"p1", "p4"}
    assert by_place["p1"]["phone"] == "01712-345678"
    assert by_place["p1"]["phone_normalized"] == "+8801712345678"
    assert by_place["p1"]["district"] == "Dhaka"
    assert by_place["p1"]["upazila"] == "Savar"
    # Same number written two ways is caught.
    assert by_place["p1"]["is_duplicate_phone"] is True
    assert by_place["p4"]["is_duplicate_phone"] is True
    assert by_place["p2"]["is_duplicate_phone"] is False
    # A number is never invented.
    assert by_place["p3"]["phone"] is None
    assert by_place["p3"]["has_phone"] is False


def test_lead_filters_combine(
    client: TestClient, lead_headers: dict, fake_places: FakePlaces
) -> None:
    hospitals(fake_places)
    search = run_search(client, lead_headers)
    base = f"/api/v1/lead/leads?search_id={search['id']}"

    def ids(query: str) -> list[str]:
        return [
            lead["place_id"]
            for lead in data(client.get(base + query, headers=lead_headers))["items"]
        ]

    assert sorted(ids("&preset=potential")) == ["p1", "p4"]
    assert ids("&website=with") == ["p2"]
    assert ids("&phone=without") == ["p3"]
    assert sorted(ids("&website=with&phone=with")) == ["p2"]
    assert sorted(ids("&website=without&min_rating=4")) == ["p4"]
    assert ids("&min_reviews=100") == ["p2"]
    assert sorted(ids("&duplicates=true")) == ["p1", "p4"]
    assert ids("&search=Diagnostic") == ["p4"]
    assert ids("&sort=rating&order=desc")[:2] == ["p2", "p4"]
    assert ids("&district=Chattogram") == []

    summary = data(
        client.get(
            f"/api/v1/lead/leads/summary?search_id={search['id']}", headers=lead_headers
        )
    )
    assert summary["potential"] == 2
    assert summary["duplicate_phones"] == 1
    assert summary["districts"] == ["Dhaka"]


def test_another_users_search_and_leads_are_invisible(
    client: TestClient,
    lead_headers: dict,
    other_lead_headers: dict,
    fake_places: FakePlaces,
) -> None:
    hospitals(fake_places)
    search = run_search(client, lead_headers)
    lead_id = data(client.get("/api/v1/lead/leads", headers=lead_headers))["items"][0][
        "id"
    ]

    assert (
        client.get(
            f"/api/v1/lead/searches/{search['id']}", headers=other_lead_headers
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/lead/leads?search_id={search['id']}", headers=other_lead_headers
        ).status_code
        == 404
    )
    assert (
        data(client.get("/api/v1/lead/leads", headers=other_lead_headers))["total"] == 0
    )
    assert (
        client.get(
            f"/api/v1/lead/leads/{lead_id}", headers=other_lead_headers
        ).status_code
        == 404
    )
    saved = client.post(
        "/api/v1/lead/saved-leads",
        json={"lead_ids": [lead_id]},
        headers=other_lead_headers,
    )
    assert data(saved) == {"saved": 0, "already_saved": 0, "not_found": 1}


def test_unknown_location_is_rejected(
    client: TestClient, lead_headers: dict, fake_places: FakePlaces
) -> None:
    response = client.post(
        "/api/v1/lead/searches",
        json={
            "keyword": "Clinic",
            "locations": [{"division": "dhaka", "district": "atlantis"}],
        },
        headers=lead_headers,
    )
    assert response.status_code == 422
    assert "atlantis" in response.json()["error"]


def test_all_bangladesh_fans_out_and_stops_at_the_per_search_cap(
    client: TestClient,
    lead_headers: dict,
    fake_places: FakePlaces,
    db_session: MongoSession,
) -> None:
    settings_row = LeadFinderSettings(
        registration_enabled=False, daily_request_quota=300, max_requests_per_search=5
    )
    db_session.add(settings_row)
    db_session.commit()
    fake_places.default_pages = [
        [place("x1", "Somewhere Pharmacy", phone_display="01811-000000")]
    ]

    search = run_search(
        client, lead_headers, keyword="Pharmacy", category="pharmacy", locations=[]
    )

    assert search["total_targets"] == 64
    assert search["status"] == "partial"
    assert search["api_requests"] == 5
    assert search["completed_targets"] == 5
    assert "per-search limit" in search["error_message"]
    assert search["location_label"] == "All Bangladesh"


def test_daily_quota_is_enforced(
    client: TestClient,
    lead_headers: dict,
    fake_places: FakePlaces,
    db_session: MongoSession,
) -> None:
    db_session.add(
        LeadFinderSettings(
            registration_enabled=False,
            daily_request_quota=2,
            max_requests_per_search=90,
        )
    )
    db_session.commit()
    hospitals(fake_places)
    first = run_search(client, lead_headers)
    assert first["api_requests"] == 2

    second = client.post(
        "/api/v1/lead/searches",
        json={"keyword": "Clinic", "locations": [SAVAR]},
        headers=lead_headers,
    )
    assert second.status_code == 429
    assert second.headers.get("retry-after")
    overview = data(client.get("/api/v1/lead/overview", headers=lead_headers))
    assert overview["quota"]["remaining"] == 0


def test_missing_api_key_is_a_clear_error(
    client: TestClient, lead_headers: dict, fake_places: FakePlaces
) -> None:
    fake_places.configured = False
    response = client.post(
        "/api/v1/lead/searches",
        json={"keyword": "Hotel", "locations": [SAVAR]},
        headers=lead_headers,
    )
    assert response.status_code == 502
    assert "GOOGLE_MAPS_API_KEY" in response.json()["error"]


def test_a_refused_key_fails_the_search_with_googles_reason(
    client: TestClient, lead_headers: dict, fake_places: FakePlaces
) -> None:
    fake_places.error = PlacesApiError(403, "Google refused the API key.")
    search = run_search(client, lead_headers)
    assert search["status"] == "failed"
    assert "refused" in search["error_message"]


def test_history_rerun_and_delete(
    client: TestClient, lead_headers: dict, fake_places: FakePlaces
) -> None:
    hospitals(fake_places)
    first = run_search(client, lead_headers)
    rerun = client.post(
        f"/api/v1/lead/searches/{first['id']}/rerun", headers=lead_headers
    )
    assert rerun.status_code == 202
    assert data(rerun)["keyword"] == "Hospital"
    assert data(rerun)["locations"][0]["label"] == "Savar, Dhaka"

    history = data(client.get("/api/v1/lead/searches", headers=lead_headers))
    assert history["total"] == 2

    assert (
        client.delete(
            f"/api/v1/lead/searches/{first['id']}", headers=lead_headers
        ).status_code
        == 204
    )
    assert data(client.get("/api/v1/lead/searches", headers=lead_headers))["total"] == 1


# ------------------------------------------------------------- saved leads


def test_save_status_notes_and_unsave(
    client: TestClient, lead_headers: dict, fake_places: FakePlaces
) -> None:
    hospitals(fake_places)
    search = run_search(client, lead_headers)
    leads = data(
        client.get("/api/v1/lead/leads?preset=potential", headers=lead_headers)
    )["items"]
    ids = [lead["id"] for lead in leads]

    first = client.post(
        "/api/v1/lead/saved-leads",
        json={"lead_ids": ids, "search_id": search["id"]},
        headers=lead_headers,
    )
    assert data(first) == {"saved": 2, "already_saved": 0, "not_found": 0}
    again = client.post(
        "/api/v1/lead/saved-leads", json={"lead_ids": ids}, headers=lead_headers
    )
    assert data(again) == {"saved": 0, "already_saved": 2, "not_found": 0}

    saved = data(client.get("/api/v1/lead/saved-leads", headers=lead_headers))
    assert saved["total"] == 2
    saved_id = saved["items"][0]["id"]

    updated = client.patch(
        f"/api/v1/lead/saved-leads/{saved_id}",
        json={"status": "contacted"},
        headers=lead_headers,
    )
    assert data(updated)["status"] == "contacted"

    noted = client.post(
        f"/api/v1/lead/saved-leads/{saved_id}/notes",
        json={"body": "Called; ask for the admin officer."},
        headers=lead_headers,
    )
    assert noted.status_code == 201
    note_id = data(noted)["notes"][0]["id"]
    after_delete = client.delete(
        f"/api/v1/lead/saved-leads/{saved_id}/notes/{note_id}", headers=lead_headers
    )
    assert data(after_delete)["notes"] == []

    marked = data(
        client.get(f"/api/v1/lead/leads?search_id={search['id']}", headers=lead_headers)
    )
    statuses = {
        lead["saved_status"] for lead in marked["items"] if lead["saved_lead_id"]
    }
    assert statuses == {"new", "contacted"}

    overview = data(client.get("/api/v1/lead/overview", headers=lead_headers))
    assert overview["stats"]["saved_leads"] == 2
    assert overview["stats"]["potential_leads"] == 2
    assert overview["saved_by_status"]["contacted"] == 1

    assert (
        client.delete(
            f"/api/v1/lead/saved-leads/{saved_id}", headers=lead_headers
        ).status_code
        == 204
    )
    assert (
        data(client.get("/api/v1/lead/saved-leads", headers=lead_headers))["total"] == 1
    )


# ----------------------------------------------------------------- exports


def test_exports_in_every_format_are_recorded(
    client: TestClient, lead_headers: dict, fake_places: FakePlaces
) -> None:
    hospitals(fake_places)
    search = run_search(client, lead_headers)

    csv = client.post(
        "/api/v1/lead/exports",
        json={
            "format": "csv",
            "scope": "search",
            "search_id": search["id"],
            "website": "without",
            "phone": "with",
        },
        headers=lead_headers,
    )
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv.headers["content-disposition"]
    text = csv.content.decode("utf-8-sig")
    assert "Ashulia General Hospital" in text
    assert "City Care Hospital" not in text
    assert csv.headers["x-export-rows"] == "2"

    xlsx = client.post(
        "/api/v1/lead/exports",
        json={"format": "xlsx", "scope": "leads"},
        headers=lead_headers,
    )
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"

    lead_id = data(client.get("/api/v1/lead/leads", headers=lead_headers))["items"][0][
        "id"
    ]
    pdf = client.post(
        "/api/v1/lead/exports",
        json={"format": "pdf", "scope": "selection", "lead_ids": [lead_id]},
        headers=lead_headers,
    )
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"

    unique = client.post(
        "/api/v1/lead/exports",
        json={
            "format": "csv",
            "scope": "leads",
            "phone": "with",
            "unique_phones": True,
        },
        headers=lead_headers,
    )
    assert unique.headers["x-export-rows"] == "2"  # p1 and p4 share a number

    history = data(client.get("/api/v1/lead/exports", headers=lead_headers))
    assert history["total"] == 4
    assert history["items"][-1]["filters"] == {
        "search_id": search["id"],
        "website": "without",
        "phone": "with",
    }


def test_empty_export_is_refused(client: TestClient, lead_headers: dict) -> None:
    response = client.post(
        "/api/v1/lead/exports",
        json={"format": "csv", "scope": "saved"},
        headers=lead_headers,
    )
    assert response.status_code == 422


def test_csv_defuses_formula_injection(
    client: TestClient, lead_headers: dict, fake_places: FakePlaces
) -> None:
    fake_places.default_pages = [
        [place("evil", '=HYPERLINK("http://x")', phone_display="01711-111111")]
    ]
    run_search(client, lead_headers)
    csv = client.post(
        "/api/v1/lead/exports", json={"format": "csv"}, headers=lead_headers
    )
    assert "'=HYPERLINK" in csv.content.decode("utf-8-sig")


# --------------------------------------------------------- storage policy


def test_expired_google_content_is_purged_and_can_be_refreshed(
    client: TestClient,
    lead_headers: dict,
    fake_places: FakePlaces,
    db_session: MongoSession,
) -> None:
    hospitals(fake_places)
    run_search(client, lead_headers)
    lead = db_session.load(
        BusinessLead, db_session.collection(BusinessLead).find_one({"place_id": "p1"})
    )
    assert lead is not None
    lead.content_expires_at = utc_now() - timedelta(days=1)
    db_session.add(lead)
    db_session.commit()

    purged, _ = asyncio.run(SearchMaintenanceUseCase(db_session).execute())
    assert purged == 1

    row = data(client.get(f"/api/v1/lead/leads/{lead.id}", headers=lead_headers))
    assert row["content_expired"] is True
    assert row["name"] is None and row["phone"] is None
    assert row["place_id"] == "p1"  # the place ID is kept
    assert row["district"] == "Dhaka"  # our own attribution is kept

    fake_places.details["p1"] = place(
        "p1", "Ashulia General Hospital", phone_display="01712-345678"
    )
    refreshed = client.post(
        f"/api/v1/lead/leads/{lead.id}/refresh", headers=lead_headers
    )
    assert refreshed.status_code == 200
    assert data(refreshed)["content_expired"] is False
    assert data(refreshed)["phone"] == "01712-345678"


def test_account_settings_for_lead_finders(
    client: TestClient, lead_headers: dict
) -> None:
    updated = client.patch(
        "/api/v1/lead/account", json={"name": "Rafi Ahmed"}, headers=lead_headers
    )
    assert data(updated)["name"] == "Rafi Ahmed"
    wrong = client.post(
        "/api/v1/lead/account/password",
        json={
            "current_password": "not-it-at-all",
            "new_password": "another-long-password",
        },
        headers=lead_headers,
    )
    assert wrong.status_code == 422
