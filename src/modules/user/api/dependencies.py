"""User module dependencies for dependency injection."""

from fastapi import Depends
from src.shared.infrastructure.database import MongoSession

from src.shared.infrastructure.database import get_db

from ..application.use_cases.account_use_cases import (
    ChangePasswordUseCase,
    UpdateAccountUseCase,
)
from ..application.use_cases.user_use_cases import (
    CreateUserUseCase,
    GetUserUseCase,
    ListUsersUseCase,
    UpdateUserUseCase,
)


def get_list_users_use_case(db: MongoSession = Depends(get_db)) -> ListUsersUseCase:
    """Get the staff-list use case with the shared DB session."""
    return ListUsersUseCase(db)


def get_get_user_use_case(db: MongoSession = Depends(get_db)) -> GetUserUseCase:
    """Get the single-user use case with the shared DB session."""
    return GetUserUseCase(db)


def get_create_user_use_case(db: MongoSession = Depends(get_db)) -> CreateUserUseCase:
    """Get the create-user use case with the shared DB session."""
    return CreateUserUseCase(db)


def get_update_user_use_case(db: MongoSession = Depends(get_db)) -> UpdateUserUseCase:
    """Get the update-user use case with the shared DB session."""
    return UpdateUserUseCase(db)


def get_update_account_use_case(
    db: MongoSession = Depends(get_db),
) -> UpdateAccountUseCase:
    """Get the self-service profile use case with the shared DB session."""
    return UpdateAccountUseCase(db)


def get_change_password_use_case(
    db: MongoSession = Depends(get_db),
) -> ChangePasswordUseCase:
    """Get the self-service password use case with the shared DB session."""
    return ChangePasswordUseCase(db)
