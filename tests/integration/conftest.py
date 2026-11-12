"""
Integration test fixtures.

Runs the real FastAPI app over HTTP against a throwaway in-memory MongoDB
(mongomock), with every declared index — unique ones included — created on
it. It exercises middleware -> routing -> auth -> use case -> repository end
to end without a MongoDB server or the network.

Three seams are swapped so the suite needs no network and no threads:

- the task dispatcher runs background work INLINE, so a manual collection run
  has finished by the time the request returns;
- background work opens its session through `get_session_factory`, pointed at
  this test's database;
- connectors are replaced per test with `FakeConnector` (see `fake_source`).
"""

from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Optional
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
import mongomock

from src.api.app import create_app
from src.modules.collection.domain.services.job_connector import ConnectorResult
from src.modules.collection.domain.value_objects.collected_job import CollectedJob
from src.modules.collection.infrastructure.external.connectors import registry
from src.modules.job.domain.entities.job import Job
from src.modules.job.domain.enums.employment_type import EmploymentType
from src.modules.job.domain.services.fingerprint import job_fingerprint
from src.modules.job_source.domain.entities.job_source import JobSource
from src.modules.job_source.domain.enums.source_type import SourceType
from src.modules.lead_finder.api.dependencies import get_places_gateway_factory
from src.modules.lead_finder.domain.value_objects.place_record import PlaceRecord
from src.modules.recommendation.api.dependencies import get_job_scorer
from src.modules.recommendation.infrastructure.scorers.heuristic_scorer import (
    HeuristicScorer,
)
from src.modules.user.domain.entities.user import User
from src.modules.user.domain.enums.user_role import UserRole
from src.modules.user.domain.enums.user_status import UserStatus
from src.shared.infrastructure.database import (
    MongoSession,
    ensure_indexes,
    get_db,
    get_session_factory,
)
from src.shared.infrastructure.security.password_hasher import hash_password
from src.shared.infrastructure.security.rate_limiter import (
    login_limiter,
    lead_export_limiter,
    lead_refresh_limiter,
    lead_search_limiter,
    manual_run_limiter,
    password_change_limiter,
    recommendation_limiter,
    register_limiter,
)
from src.shared.infrastructure.tasks.dispatcher import (
    InlineTaskDispatcher,
    get_task_dispatcher,
)

TEST_PASSWORD = "integration-test-password"


@pytest.fixture(scope="session")
def _hashed_password() -> str:
    """Hash once per session — bcrypt at cost 12 is ~250ms a call."""
    return hash_password(TEST_PASSWORD)


@pytest.fixture
def db_session() -> Generator[MongoSession, None, None]:
    """An isolated in-memory database, rebuilt for every test, with every
    entity's indexes created on it (so unique constraints are enforced)."""
    client = mongomock.MongoClient(tz_aware=True)
    database = client["nexthire_test"]
    ensure_indexes(database)
    session = MongoSession(database)
    try:
        yield session
    finally:
        session.close()
        client.close()


@pytest.fixture
def make_user(db_session: MongoSession, _hashed_password: str) -> Callable[..., User]:
    """Persist a user. Every one signs in with TEST_PASSWORD."""

    def factory(
        email: str,
        role: UserRole = UserRole.SEEKER,
        status: UserStatus = UserStatus.ACTIVE,
    ) -> User:
        user = User(
            name=email.split("@")[0].replace(".", " ").title(),
            email=email,
            password_hash=_hashed_password,
            role=role,
            status=status,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return factory


@pytest.fixture
def admin(make_user: Callable[..., User]) -> User:
    """An admin."""
    return make_user("admin@nexthire.dev", role=UserRole.ADMIN)


@pytest.fixture
def seeker(make_user: Callable[..., User]) -> User:
    """A job seeker."""
    return make_user("maya@nexthire.dev")


@pytest.fixture
def other_seeker(make_user: Callable[..., User]) -> User:
    """A second seeker, for the ownership tests."""
    return make_user("daniel@nexthire.dev")


@pytest.fixture
def client(db_session: MongoSession) -> Generator[TestClient, None, None]:
    """The real app, wired to the test database.

    The limiters are module-level singletons, so they are cleared per test:
    otherwise the sixth sign-in of a run gets a 429 for a correct password — a
    failure that depends on test ORDER, the worst kind to debug.
    """
    for limiter in (
        login_limiter,
        register_limiter,
        password_change_limiter,
        recommendation_limiter,
        manual_run_limiter,
        lead_search_limiter,
        lead_refresh_limiter,
        lead_export_limiter,
    ):
        limiter._windows.clear()

    app = create_app()

    def override_get_db() -> Generator[MongoSession, None, None]:
        yield db_session

    @contextmanager
    def test_session_context() -> Iterator[MongoSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: test_session_context
    app.dependency_overrides[get_task_dispatcher] = InlineTaskDispatcher
    app.dependency_overrides[get_job_scorer] = HeuristicScorer

    with patch("src.api.app.ensure_indexes"):
        with TestClient(app) as test_client:
            yield test_client


def login(client: TestClient, user: User) -> dict[str, str]:
    """Sign in and return the Authorization header."""
    response = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


@pytest.fixture
def admin_headers(client: TestClient, admin: User) -> dict[str, str]:
    """Signed-in admin."""
    return login(client, admin)


@pytest.fixture
def seeker_headers(client: TestClient, seeker: User) -> dict[str, str]:
    """Signed-in seeker."""
    return login(client, seeker)


@pytest.fixture
def other_seeker_headers(client: TestClient, other_seeker: User) -> dict[str, str]:
    """Signed-in second seeker."""
    return login(client, other_seeker)


# ---------------------------------------------------------------------------
# Sources and jobs
# ---------------------------------------------------------------------------


@pytest.fixture
def make_source(db_session: MongoSession) -> Callable[..., JobSource]:
    """Persist a source directly."""

    def factory(slug: str = "remotive-dev", **overrides: Any) -> JobSource:
        values: dict[str, Any] = {
            "name": slug.replace("-", " ").title(),
            "slug": slug,
            "source_type": SourceType.REMOTIVE,
            "config": {"search": "python"},
            "schedule_minutes": 60,
        }
        values.update(overrides)
        source = JobSource(**values)
        db_session.add(source)
        db_session.commit()
        db_session.refresh(source)
        return source

    return factory


@pytest.fixture
def make_job(
    db_session: MongoSession, make_source: Callable[..., JobSource]
) -> Callable[..., Job]:
    """Persist a job directly. A default source is created on first use."""
    default_source: list[JobSource] = []

    def factory(title: str = "Python Developer", **overrides: Any) -> Job:
        if "source_id" not in overrides:
            if not default_source:
                default_source.append(make_source("fixture-source"))
            overrides["source_id"] = default_source[0].id
        now = datetime.now(UTC)
        company = overrides.pop("company", "Acme")
        location = overrides.pop("location", "Berlin, Germany")
        values: dict[str, Any] = {
            "external_id": overrides.pop("external_id", uuid4().hex),
            "title": title,
            "company": company,
            "location": location,
            "url": "https://jobs.example.com/" + uuid4().hex,
            "description": "We need Python and FastAPI experience with PostgreSQL.",
            "tags": ["python", "fastapi"],
            "employment_type": EmploymentType.FULL_TIME,
            "posted_at": now - timedelta(days=1),
            "first_seen_at": now,
            "last_seen_at": now,
            "fingerprint": job_fingerprint(title, company, location),
        }
        values.update(overrides)
        job = Job(**values)
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)
        return job

    return factory


def collected(
    external_id: str, title: str, company: str = "Acme", **extra: Any
) -> CollectedJob:
    """A connector result row."""
    return CollectedJob(
        external_id=external_id,
        title=title,
        company=company,
        url=f"https://jobs.example.com/{external_id}",
        description=extra.pop("description", f"{title} using Python."),
        **extra,
    )


class FakeConnector:
    """Returns canned jobs, or raises, without touching the network."""

    def __init__(
        self,
        jobs: Optional[list[CollectedJob]] = None,
        *,
        skipped: int = 0,
        error: Optional[Exception] = None,
    ) -> None:
        self.jobs = jobs or []
        self.skipped = skipped
        self.error = error
        self.calls = 0

    async def fetch(self, config: dict[str, Any], limit: int) -> ConnectorResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return ConnectorResult(jobs=list(self.jobs[:limit]), skipped=self.skipped)


@pytest.fixture
def fake_connector(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeConnector]:
    """Install a fake connector for a source type for this test."""

    def install(
        connector: FakeConnector, source_type: SourceType = SourceType.REMOTIVE
    ) -> FakeConnector:
        monkeypatch.setitem(registry.CONNECTORS, source_type, lambda: connector)
        return connector

    return install


# ---------------------------------------------------------------------------
# Lead Finder
# ---------------------------------------------------------------------------


def place(place_id: str, name: str, **extra: Any) -> PlaceRecord:
    """A Places API result row."""
    values: dict[str, Any] = {
        "place_id": place_id,
        "name": name,
        "primary_category": "Hospital",
        "primary_type": "hospital",
        "formatted_address": f"{name} Road, Dhaka",
        "google_maps_uri": f"https://maps.google.com/?cid={place_id}",
        "latitude": 23.8,
        "longitude": 90.4,
    }
    values.update(extra)
    return PlaceRecord(**values)


class FakePlaces:
    """Stands in for Google. ``pages`` maps a query substring to result pages.

    Every gateway it makes counts its own requests, as the real client does.
    """

    def __init__(self) -> None:
        self.pages: dict[str, list[list[PlaceRecord]]] = {}
        self.default_pages: list[list[PlaceRecord]] = []
        self.details: dict[str, Optional[PlaceRecord]] = {}
        self.error: Optional[Exception] = None
        self.configured = True
        self.queries: list[str] = []

    def factory(self) -> "FakeGateway":
        return FakeGateway(self)


class FakeGateway:
    def __init__(self, owner: FakePlaces) -> None:
        self.owner = owner
        self.requests_made = 0

    @property
    def is_configured(self) -> bool:
        return self.owner.configured

    async def text_search(
        self, query: str, page_token: Optional[str] = None
    ) -> tuple[list[PlaceRecord], Optional[str]]:
        self.requests_made += 1
        self.owner.queries.append(query)
        if self.owner.error is not None:
            raise self.owner.error
        pages = next(
            (pages for key, pages in self.owner.pages.items() if key in query),
            self.owner.default_pages,
        )
        index = int(page_token or 0)
        if index >= len(pages):
            return [], None
        token = str(index + 1) if index + 1 < len(pages) else None
        return list(pages[index]), token

    async def place_details(self, place_id: str) -> Optional[PlaceRecord]:
        self.requests_made += 1
        return self.owner.details.get(place_id)


@pytest.fixture
def fake_places(client: TestClient) -> FakePlaces:
    """Replace Google for this test."""
    fake = FakePlaces()
    client.app.dependency_overrides[get_places_gateway_factory] = lambda: fake.factory  # type: ignore[attr-defined]
    return fake


def lead_login(client: TestClient, user: User) -> dict[str, str]:
    """Sign in through the Lead Finder sign-in."""
    response = client.post(
        "/api/v1/auth/lead-finder/login",
        json={"email": user.email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


@pytest.fixture
def lead_finder(make_user: Callable[..., User]) -> User:
    """A Lead Finder user."""
    return make_user("rafi@leads.dev", role=UserRole.LEAD_FINDER)


@pytest.fixture
def other_lead_finder(make_user: Callable[..., User]) -> User:
    """A second Lead Finder user, for the ownership tests."""
    return make_user("nadia@leads.dev", role=UserRole.LEAD_FINDER)


@pytest.fixture
def lead_headers(client: TestClient, lead_finder: User) -> dict[str, str]:
    """Signed-in lead finder."""
    return lead_login(client, lead_finder)


@pytest.fixture
def other_lead_headers(client: TestClient, other_lead_finder: User) -> dict[str, str]:
    """Signed-in second lead finder."""
    return lead_login(client, other_lead_finder)
