"""Use case for signing a user out."""

from src.shared.infrastructure.logging import get_logger

from ..schemas.auth_schema import LogoutResponseSchema

logger = get_logger(__name__)


class LogoutUseCase:
    """Sign a user out.

    No server-side revocation in v1, as in hgs-backend's identical class: the
    frontend clears the cookie. Adding a revocation store later changes only
    this class.
    """

    async def execute(self, email: str) -> LogoutResponseSchema:
        """Record the sign-out and acknowledge it."""
        logger.info(f"Signed out: {email}")
        return LogoutResponseSchema()
