"""Use case for a job seeker creating their own account."""

from pymongo.errors import DuplicateKeyError

from src.modules.user.application.schemas.user_schema import UserResponseSchema
from src.modules.user.domain.entities.user import User
from src.modules.user.domain.enums.user_role import UserRole
from src.modules.user.domain.enums.user_status import UserStatus
from src.modules.user.infrastructure.repositories.user_repository import (
    UserRepository,
)
from src.shared.api.auth.jwt_handler import create_access_token
from src.shared.domain.exceptions.already_exists_error import AlreadyExistsError
from src.shared.infrastructure.logging import get_logger
from src.shared.infrastructure.security.password_hasher import hash_password
from src.shared.utils.config import settings

from ..schemas.auth_schema import LoginResponseSchema, RegisterRequestSchema

logger = get_logger(__name__)


class RegisterUseCase:
    """Create an account of a FIXED role and sign it in."""

    def __init__(self, repository: UserRepository, role: UserRole = UserRole.SEEKER):
        """Initialize use case with repository.

        Args:
            repository: User repository
            role: The role every account this instance creates gets. Bound by
                the dependency factory, never read from the request: SEEKER for
                `/auth/register`, LEAD_FINDER for `/auth/lead-finder/register`.
        """
        self.repository = repository
        self.role = role

    async def execute(self, data: RegisterRequestSchema) -> LoginResponseSchema:
        """
        Create the account and return a session, as a login would.

        The role is fixed here, never taken from the request.

        Raises:
            AlreadyExistsError: The email is already registered. This does
                reveal that an address has an account — unavoidable for a
                sign-up form that must say why it failed — so the endpoint is
                rate limited per address like login.
        """
        email = str(data.email).lower()
        if await self.repository.exists_by_email(email):
            raise AlreadyExistsError(entity_name="User", field="email", value=email)

        user = User(
            name=data.name,
            email=email,
            password_hash=hash_password(data.password),
            role=self.role,
            status=UserStatus.ACTIVE,
        )
        try:
            user = await self.repository.create(user)
        except DuplicateKeyError as e:
            # Two sign-ups with one address racing past the check above.
            raise AlreadyExistsError(
                entity_name="User", field="email", value=email
            ) from e

        assert user.id is not None
        user = await self.repository.touch_last_login(user)
        logger.info(f"Registered {user.role.value}: {user.email}")
        return LoginResponseSchema(
            access_token=create_access_token(
                user_id=user.id, email=user.email, role=user.role.value
            ),
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
            user=UserResponseSchema.model_validate(user),
        )
