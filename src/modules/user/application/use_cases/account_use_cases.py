"""Use cases behind the app's Account settings screen.

Every operation acts on the CALLER — the user resolved from the session by
`hasAccess` — never on an id from the request, so there is no ownership check
to get wrong: a seeker cannot address anyone else's account through here.
"""

from uuid import UUID

from src.shared.infrastructure.database import MongoSession

from src.shared.domain.exceptions.not_found_error import NotFoundError
from src.shared.domain.exceptions.validation_error import ValidationError
from src.shared.infrastructure.logging import get_logger
from src.shared.infrastructure.security.password_hasher import (
    hash_password,
    verify_password,
)

from ...domain.entities.user import User
from ...infrastructure.repositories.user_repository import UserRepository
from ..schemas.account_schema import (
    AccountUpdateSchema,
    PasswordChangeResponseSchema,
    PasswordChangeSchema,
)
from ..schemas.user_schema import UserResponseSchema

logger = get_logger(__name__)


class _AccountUseCase:
    """Shared lookup: the caller's own live row."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.repository = UserRepository(session)

    async def _load(self, user_id: UUID) -> User:
        user = await self.repository.get_by_id(user_id)
        if user is None or not user.is_active:
            raise NotFoundError(entity_name="User", entity_id=user_id)
        return user


class UpdateAccountUseCase(_AccountUseCase):
    """Change the caller's name or phone number."""

    async def execute(
        self, user_id: UUID, payload: AccountUpdateSchema
    ) -> UserResponseSchema:
        """Apply the partial update.

        Raises:
            NotFoundError: If the caller's row has gone (cannot normally happen —
                `hasAccess` has just read it)
        """
        user = await self._load(user_id)
        supplied = payload.model_dump(exclude_unset=True)

        if supplied.get("name") is not None:
            user.name = supplied["name"]
        if "phone" in supplied:
            user.phone = supplied["phone"]

        user.updated_by = user_id
        updated = await self.repository.update(user)
        logger.info(f"Account updated by its owner: {updated.email}")
        return UserResponseSchema.model_validate(updated)


class ChangePasswordUseCase(_AccountUseCase):
    """Replace the caller's password, given the current one."""

    async def execute(
        self, user_id: UUID, payload: PasswordChangeSchema
    ) -> PasswordChangeResponseSchema:
        """Verify, then re-hash.

        Raises:
            ValidationError: On a wrong current password (422 naming
                ``current_password`` — NOT 401, which the dashboard reads as
                "your session expired" and would sign the user out), or when the
                new password is the current one.
        """
        user = await self._load(user_id)

        if not verify_password(payload.current_password, user.password_hash):
            logger.warning(f"Password change refused, wrong current: {user.email}")
            raise ValidationError(
                entity_name="User",
                field="current_password",
                message="That is not your current password.",
            )

        if payload.new_password == payload.current_password:
            raise ValidationError(
                entity_name="User",
                field="new_password",
                message="Choose a password different from your current one.",
            )

        user.password_hash = hash_password(payload.new_password)
        user.updated_by = user_id
        await self.repository.update(user)
        logger.info(f"Password changed by its owner: {user.email}")
        return PasswordChangeResponseSchema()
