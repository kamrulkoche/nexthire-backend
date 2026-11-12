"""Unit tests for LoginUseCase."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.auth.application.schemas.auth_schema import LoginRequestSchema
from src.modules.auth.application.use_cases.login_use_case import LoginUseCase
from src.modules.user.domain.entities.user import User
from src.shared.api.auth.jwt_handler import verify_access_token
from src.shared.domain.exceptions.unauthorized_error import UnauthorizedError


def _repo(user: User | None) -> MagicMock:
    """A mock UserRepository returning `user` from get_by_email."""
    repo = MagicMock()
    repo.get_by_email = AsyncMock(return_value=user)
    repo.touch_last_login = AsyncMock(side_effect=lambda u: u)
    return repo


@pytest.mark.unit
class TestLoginUseCase:
    async def test_valid_credentials_return_a_verifiable_token(
        self, seeker: User, password: str
    ):
        result = await LoginUseCase(_repo(seeker)).execute(
            LoginRequestSchema(email=seeker.email, password=password)
        )

        assert result.token_type == "bearer"
        assert result.expires_in > 0
        assert result.user.email == seeker.email
        # The token must actually verify, and carry the role the API re-checks.
        claims = verify_access_token(result.access_token)
        assert claims["sub"] == str(seeker.id)
        assert claims["role"] == "seeker"

    async def test_login_records_last_login(self, seeker: User, password: str):
        repo = _repo(seeker)
        await LoginUseCase(repo).execute(
            LoginRequestSchema(email=seeker.email, password=password)
        )
        repo.touch_last_login.assert_awaited_once_with(seeker)

    async def test_wrong_password_and_unknown_email_fail_identically(
        self, seeker: User
    ):
        with pytest.raises(UnauthorizedError) as wrong_password:
            await LoginUseCase(_repo(seeker)).execute(
                LoginRequestSchema(email=seeker.email, password="not-the-password")
            )
        with pytest.raises(UnauthorizedError) as unknown_email:
            await LoginUseCase(_repo(None)).execute(
                LoginRequestSchema(email="nobody@nexthire.dev", password="whatever")
            )
        # Same words for both, or the message enumerates accounts.
        assert wrong_password.value.message == unknown_email.value.message

    async def test_unknown_email_still_spends_a_hash(self):
        # Returning early would make this path measurably faster than a wrong
        # password, which enumerates accounts by timing alone.
        with patch(
            "src.modules.auth.application.use_cases.login_use_case.verify_password",
            return_value=False,
        ) as verify:
            with pytest.raises(UnauthorizedError):
                await LoginUseCase(_repo(None)).execute(
                    LoginRequestSchema(email="nobody@nexthire.dev", password="x")
                )
        verify.assert_called_once()

    async def test_suspended_account_is_refused_with_its_own_message(
        self, suspended_seeker: User, password: str
    ):
        with pytest.raises(UnauthorizedError) as exc:
            await LoginUseCase(_repo(suspended_seeker)).execute(
                LoginRequestSchema(email=suspended_seeker.email, password=password)
            )
        assert "not active" in exc.value.message
