"""Unit tests for the "never leave zero admins" guard in UpdateUserUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.user.application.schemas.user_schema import UserUpdateSchema
from src.modules.user.application.use_cases.user_use_cases import UpdateUserUseCase
from src.modules.user.domain.entities.user import User
from src.shared.domain.exceptions.validation_error import ValidationError


def _use_case(target: User, other_admins: int) -> UpdateUserUseCase:
    use_case = UpdateUserUseCase(MagicMock())
    use_case.repository = MagicMock(
        get_by_id=AsyncMock(return_value=target),
        count_active_admins=AsyncMock(return_value=other_admins),
        update=AsyncMock(side_effect=lambda row: row),
    )
    return use_case


@pytest.mark.unit
class TestLastAdminGuard:
    async def test_last_admin_cannot_be_demoted(self, admin: User):
        with pytest.raises(ValidationError):
            await _use_case(admin, other_admins=0).execute(
                admin.id, UserUpdateSchema(role="seeker")
            )

    async def test_last_admin_cannot_be_deactivated(self, admin: User):
        with pytest.raises(ValidationError):
            await _use_case(admin, other_admins=0).execute(
                admin.id, UserUpdateSchema(status="inactive")
            )

    async def test_an_admin_can_be_demoted_when_another_remains(self, admin: User):
        result = await _use_case(admin, other_admins=1).execute(
            admin.id, UserUpdateSchema(role="seeker")
        )
        assert result.role.value == "seeker"

    async def test_renaming_the_last_admin_is_fine(self, admin: User):
        result = await _use_case(admin, other_admins=0).execute(
            admin.id, UserUpdateSchema(name="Renamed Admin")
        )
        assert result.name == "Renamed Admin"


@pytest.mark.unit
class TestPasswordRules:
    def test_short_password_is_rejected(self):
        with pytest.raises(Exception):
            UserUpdateSchema(password="short")

    def test_password_over_72_bytes_is_rejected(self):
        with pytest.raises(Exception):
            UserUpdateSchema(password="é" * 40)  # 80 bytes, 40 characters
