"""
Creates the initial admin account on application startup.

Ported from hgs-backend (which mirrors sp-company-backend's
SetupSuperadminService minus the Clerk half). Two scenarios: the account
exists, or it does not. An existing account is NEVER overwritten, so changing
ADMIN_PASSWORD does not reset a live password.

Credentials come from the environment ONLY (`ADMIN_EMAIL`, `ADMIN_PASSWORD`).
Every method logs rather than raising: a failed bootstrap must not take the API
down.
"""

from src.shared.infrastructure.database import MongoSession

from src.modules.user.application.schemas.user_schema import MIN_PASSWORD_LENGTH
from src.modules.user.domain.entities.user import User
from src.modules.user.domain.enums.user_role import UserRole
from src.modules.user.domain.enums.user_status import UserStatus
from src.modules.user.infrastructure.repositories.user_repository import (
    UserRepository,
)
from src.shared.infrastructure.logging import get_logger
from src.shared.infrastructure.security.password_hasher import hash_password
from src.shared.utils.config import settings

logger = get_logger(__name__)


class SetupAdminService:
    """Automatic initial-admin setup."""

    def __init__(self, db: MongoSession):
        """Initialize with a database session."""
        self.repository = UserRepository(db, User)

    def _validate_configuration(self) -> bool:
        """Check that setup is enabled and the required settings are present."""
        if not settings.setup_admin:
            logger.info("Initial admin auto-setup is disabled (SETUP_ADMIN=false)")
            return False
        if not settings.admin_email or not settings.admin_password:
            logger.warning(
                "ADMIN_EMAIL / ADMIN_PASSWORD not set — skipping admin setup"
            )
            return False
        if len(settings.admin_password) < MIN_PASSWORD_LENGTH:
            logger.error(
                f"ADMIN_PASSWORD is shorter than {MIN_PASSWORD_LENGTH} characters — "
                "refusing to create the initial admin with a weak password"
            )
            return False
        return True

    async def setup_admin(self) -> bool:
        """Create the initial admin if absent.

        Returns:
            True if an account was created
        """
        if not self._validate_configuration():
            return False

        assert settings.admin_email is not None
        assert settings.admin_password is not None

        try:
            existing = await self.repository.get_by_email(settings.admin_email)
            if existing is not None:
                logger.info(
                    f"Initial admin already exists ({existing.email}) — untouched"
                )
                return False

            created = await self.repository.create(
                User(
                    name=settings.admin_name,
                    email=settings.admin_email,
                    password_hash=hash_password(settings.admin_password),
                    role=UserRole.ADMIN,
                    status=UserStatus.ACTIVE,
                )
            )
            logger.info(f"Created initial admin account: {created.email}")
            return True
        except Exception as e:
            logger.error(f"Initial admin setup failed: {e}", exc_info=True)
            return False
