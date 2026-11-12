"""Use case for returning the signed-in user's profile."""

from uuid import UUID

from src.modules.user.application.schemas.user_schema import UserResponseSchema
from src.modules.user.infrastructure.repositories.user_repository import (
    UserRepository,
)
from src.shared.domain.exceptions.not_found_error import NotFoundError


class GetCurrentUserUseCase:
    """Retrieve the current user's profile."""

    def __init__(self, repository: UserRepository):
        """Initialize use case with repository."""
        self.repository = repository

    async def execute(self, user_id: UUID) -> UserResponseSchema:
        """
        Get the profile.

        Re-reads rather than echoing the entity the auth dependency resolved, so
        the response reflects any change made during this request.

        Raises:
            NotFoundError: If the user no longer exists
        """
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise NotFoundError(entity_name="User", entity_id=str(user_id))
        return UserResponseSchema.model_validate(user)
