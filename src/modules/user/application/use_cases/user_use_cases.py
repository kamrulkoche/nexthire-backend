"""Use cases behind the Users screen.

One module rather than one file per operation, as hgs-backend does for
`contact`: a list, a read, a create and an update over one table share their
rules closely enough that splitting them would scatter the "last admin" guard.

Every operation here is admin-only, which the route enforces with
`hasAccess(roles=[ADMIN])`. The rules below are the ones a role check cannot
express — they depend on which row is being changed.
"""

from typing import List, Optional, Tuple
from uuid import UUID

from pymongo.errors import DuplicateKeyError
from src.shared.infrastructure.database import MongoSession

from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.already_exists_error import AlreadyExistsError
from src.shared.domain.exceptions.not_found_error import NotFoundError
from src.shared.domain.exceptions.validation_error import ValidationError
from src.shared.infrastructure.audit_context import get_current_user_id
from src.shared.infrastructure.logging import get_logger
from src.shared.infrastructure.security.password_hasher import hash_password

from ...domain.entities.user import User
from ...domain.enums.user_role import UserRole
from ...domain.enums.user_status import UserStatus
from ...infrastructure.repositories.user_repository import UserRepository
from ..schemas.user_schema import (
    UserCreateSchema,
    UserResponseSchema,
    UserUpdateSchema,
)

logger = get_logger(__name__)


class ListUsersUseCase:
    """Page through accounts."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.repository = UserRepository(session)

    async def execute(
        self,
        params: ListQueryParams,
        *,
        role: Optional[UserRole] = None,
        status: Optional[UserStatus] = None,
    ) -> Tuple[List[UserResponseSchema], int]:
        """List users.

        Returns:
            ``(items, total)``
        """
        rows, total = await self.repository.list_paginated(
            params, role=role, status=status
        )
        return [UserResponseSchema.model_validate(row) for row in rows], total


class GetUserUseCase:
    """Read one account."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.repository = UserRepository(session)

    async def execute(self, user_id: UUID) -> UserResponseSchema:
        """Fetch a user by id.

        Raises:
            NotFoundError: If no live user has this id
        """
        user = await self.repository.get_by_id(user_id)
        if user is None or not user.is_active:
            raise NotFoundError(entity_name="User", entity_id=user_id)
        return UserResponseSchema.model_validate(user)


class CreateUserUseCase:
    """Add an account."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.session = session
        self.repository = UserRepository(session)

    async def execute(self, payload: UserCreateSchema) -> UserResponseSchema:
        """Create the account.

        Raises:
            AlreadyExistsError: If the email is taken. Checked up front for a
                clear message, and again from the unique index, which is the
                only thing that sees a concurrent insert.
        """
        email = str(payload.email).lower()
        if await self.repository.exists_by_email(email):
            raise AlreadyExistsError(entity_name="User", field="email", value=email)

        actor_id = get_current_user_id()
        user = User(
            name=payload.name,
            email=email,
            phone=payload.phone,
            role=payload.role,
            status=UserStatus.ACTIVE,
            password_hash=hash_password(payload.password),
            created_by=actor_id,
            updated_by=actor_id,
        )

        try:
            created = await self.repository.create(user)
        except DuplicateKeyError as e:
            self.session.rollback()
            raise AlreadyExistsError(
                entity_name="User", field="email", value=email
            ) from e

        logger.info(
            f"User created: {created.email} ({created.role.value}) by {actor_id}"
        )
        return UserResponseSchema.model_validate(created)


class UpdateUserUseCase:
    """Change an account's details, role, status or password."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.repository = UserRepository(session)

    async def execute(
        self, user_id: UUID, payload: UserUpdateSchema
    ) -> UserResponseSchema:
        """Apply the partial update.

        Raises:
            NotFoundError: If no live user has this id
            ValidationError: If the change would leave no active admin. Both a
                demotion and a deactivation count — either one, applied to the
                last admin, locks everybody out of user management for good.
        """
        user = await self.repository.get_by_id(user_id)
        if user is None or not user.is_active:
            raise NotFoundError(entity_name="User", entity_id=user_id)

        supplied = payload.model_dump(exclude_unset=True)

        loses_admin = (
            user.role == UserRole.ADMIN
            and user.status == UserStatus.ACTIVE
            and (
                supplied.get("role") not in (None, UserRole.ADMIN)
                or supplied.get("status") not in (None, UserStatus.ACTIVE)
            )
        )
        if (
            loses_admin
            and await self.repository.count_active_admins(exclude_id=user_id) == 0
        ):
            raise ValidationError(
                entity_name="User",
                field="role" if "role" in supplied else "status",
                message="This is the only active admin. Make someone else an "
                "admin first.",
            )

        for field in ("name", "phone", "role", "status"):
            if field in supplied and (supplied[field] is not None or field == "phone"):
                setattr(user, field, supplied[field])

        if payload.password:
            user.password_hash = hash_password(payload.password)

        user.updated_by = get_current_user_id()
        updated = await self.repository.update(user)
        logger.info(f"User updated: {updated.email}")
        return UserResponseSchema.model_validate(updated)
