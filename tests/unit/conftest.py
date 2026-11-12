"""
Unit-test fixtures.

As in hgs-backend, unit tests build mock repositories inline rather than
touching a database; these fixtures exist for the entities and passwords most
of them need.
"""

from uuid import uuid4

import pytest

from src.modules.user.domain.entities.user import User
from src.modules.user.domain.enums.user_role import UserRole
from src.modules.user.domain.enums.user_status import UserStatus
from src.shared.infrastructure.security.password_hasher import hash_password

#: Long enough for the 12-character floor, short enough for bcrypt's 72 bytes.
TEST_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def password() -> str:
    """The plaintext matching every fixture user's hash."""
    return TEST_PASSWORD


@pytest.fixture(scope="session")
def hashed_password() -> str:
    """Hash once per session — bcrypt at cost 12 is ~250ms a call."""
    return hash_password(TEST_PASSWORD)


def _user(
    hashed: str, *, role: UserRole, status: UserStatus = UserStatus.ACTIVE, email: str
) -> User:
    return User(
        id=uuid4(),
        name=email.split("@")[0].title(),
        email=email,
        password_hash=hashed,
        role=role,
        status=status,
        is_active=True,
    )


@pytest.fixture
def admin(hashed_password: str) -> User:
    """An admin."""
    return _user(hashed_password, role=UserRole.ADMIN, email="admin@nexthire.dev")


@pytest.fixture
def seeker(hashed_password: str) -> User:
    """An seeker."""
    return _user(hashed_password, role=UserRole.SEEKER, email="seeker@nexthire.dev")


@pytest.fixture
def other_seeker(hashed_password: str) -> User:
    """A second seeker, for the ownership tests."""
    return _user(hashed_password, role=UserRole.SEEKER, email="other@nexthire.dev")


@pytest.fixture
def suspended_seeker(hashed_password: str) -> User:
    """An seeker whose password is right but whose account is suspended."""
    return _user(
        hashed_password,
        role=UserRole.SEEKER,
        status=UserStatus.SUSPENDED,
        email="suspended@nexthire.dev",
    )
