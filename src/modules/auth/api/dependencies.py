"""Auth module dependencies for dependency injection."""

from fastapi import Depends
from src.shared.infrastructure.database import MongoSession

from src.modules.user.domain.entities.user import User
from src.modules.user.infrastructure.repositories.user_repository import (
    UserRepository,
)
from src.shared.infrastructure.database import get_db

from ..application.use_cases.get_current_user_use_case import GetCurrentUserUseCase
from ..application.use_cases.login_use_case import LoginUseCase
from ..application.use_cases.logout_use_case import LogoutUseCase
from ..application.use_cases.register_use_case import RegisterUseCase


def get_user_repository(db: MongoSession = Depends(get_db)) -> UserRepository:
    """Get a user repository bound to the request's session."""
    return UserRepository(db, User)


def get_login_use_case(
    repository: UserRepository = Depends(get_user_repository),
) -> LoginUseCase:
    """Get login use case."""
    return LoginUseCase(repository)


def get_get_current_user_use_case(
    repository: UserRepository = Depends(get_user_repository),
) -> GetCurrentUserUseCase:
    """Get current-user use case."""
    return GetCurrentUserUseCase(repository)


def get_logout_use_case() -> LogoutUseCase:
    """Get logout use case."""
    return LogoutUseCase()


def get_register_use_case(
    repository: UserRepository = Depends(get_user_repository),
) -> RegisterUseCase:
    """Get register use case."""
    return RegisterUseCase(repository)
