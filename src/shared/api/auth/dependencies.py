"""
Authentication dependencies for FastAPI endpoints.

Provides dependency injection for authentication and authorization:
- get_current_user: Extract and validate the user from a JWT
- hasAccess: Universal access control with a role list

Ported from hgs-backend, which kept sp-company-backend's exact name and
signature shape for ``hasAccess`` so route code reads identically across the
projects. NextHire AI keeps it too; the only change is the entity it resolves
(``User`` with two roles rather than ``AdminUser`` with one).

Roles are checked here. OWNERSHIP — whose rows these are —
is not: only the use case has the row, so it raises ``ForbiddenError`` there.
"""

from typing import Callable, List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.modules.user.domain.entities.user import User
from src.modules.user.domain.enums.user_role import UserRole
from src.modules.user.infrastructure.repositories.user_repository import (
    UserRepository,
)
from src.shared.infrastructure.audit_context import set_current_user
from src.shared.infrastructure.database import MongoSession, get_db
from src.shared.infrastructure.logging import get_logger

from .jwt_handler import extract_user_context, verify_access_token

logger = get_logger(__name__)

# auto_error=False so a MISSING token yields our 401 rather than FastAPI's
# default 403 — "you did not authenticate" and "you may not do this" are
# different answers and the frontend routes them differently.
security = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    """Build a 401 carrying the WWW-Authenticate challenge."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _resolve_current_user(
    credentials: Optional[HTTPAuthorizationCredentials],
    db: MongoSession,
) -> User:
    """
    Shared implementation behind ``get_current_user`` and ``hasAccess``.

    1. Token present?
    2. Signature and expiry valid? (``verify_access_token``)
    3. Does the subject still exist in the database?
    4. Is the account still allowed to authenticate?
    5. Does the token's role claim still match the database?

    Steps 3-5 are what make revocation immediate: deactivating an account or
    changing their role takes effect on the very next request rather than when
    their token expires, because the token is never trusted on its own.

    Raises:
        HTTPException: 401 if any step fails
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Not authenticated.")

    payload = verify_access_token(credentials.credentials)
    context = extract_user_context(payload)

    repository = UserRepository(db, User)
    user = await repository.get_by_id(context["user_id"])

    if user is None:
        logger.warning(f"Token for unknown user: {context['user_id']}")
        raise _unauthorized("Account no longer exists.")

    if not user.can_authenticate:
        logger.warning(
            f"Rejected request for {user.email}: "
            f"status={user.status}, is_active={user.is_active}"
        )
        raise _unauthorized("This account is not active. Please contact an admin.")

    # A token minted before a demotion must not keep its old privileges.
    if context["role"] and context["role"] != user.role.value:
        logger.warning(
            f"Role mismatch for {user.email}: "
            f"token={context['role']}, db={user.role.value}"
        )
        raise _unauthorized("Session is no longer valid. Please sign in again.")

    # Stamp the audit context so use cases can fill created_by/updated_by.
    # Cleared by AuditContextMiddleware when the request ends.
    if user.id is not None:
        set_current_user(user.id)

    return user


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: MongoSession = Depends(get_db),
) -> User:
    """
    Get the authenticated user for the current request, whatever their role.

    Raises:
        HTTPException: 401 if authentication fails
    """
    return await _resolve_current_user(credentials, db)


def hasAccess(roles: Optional[List[UserRole]] = None) -> Callable:
    """
    Universal access control — THE authorization function for this API.

    Args:
        roles: Allowed roles. ``None`` means "any authenticated user".

    Returns:
        A FastAPI dependency returning the User

    Examples:
        # Admin only
        @router.get("")
        async def list_users(user: User = Depends(hasAccess(roles=[UserRole.ADMIN]))):
            ...

        # Any signed-in user — the repository narrows to the caller's own rows
        @router.get("")
        async def list_saved_jobs(user: User = Depends(hasAccess(roles=SIGNED_IN))):
            ...
    """

    async def dependency(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
        db: MongoSession = Depends(get_db),
    ) -> User:
        """Authenticate, then authorize against the allowed role list."""
        user = await _resolve_current_user(credentials, db)

        if roles and user.role not in roles:
            logger.warning(
                f"Forbidden: {user.email} (role={user.role.value}) attempted an "
                f"endpoint restricted to {[r.value for r in roles]}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )

        return user

    return dependency


#: The two role sets every route in this service uses. Named once so a route
#: reads `Depends(hasAccess(roles=SIGNED_IN))` and nobody retypes the list.
#: Admins are in SIGNED_IN deliberately: an admin can use every seeker screen.
ADMIN_ONLY = [UserRole.ADMIN]
SIGNED_IN = [UserRole.ADMIN, UserRole.SEEKER]

#: The Lead Finder family (`/api/v1/lead/*`). Lead finders only: admins manage
#: the product from `/admin/lead-finder` and `/admin/users`, so every lead row
#: has exactly one kind of owner.
LEAD_FINDER_ONLY = [UserRole.LEAD_FINDER]


__all__ = [
    "ADMIN_ONLY",
    "LEAD_FINDER_ONLY",
    "SIGNED_IN",
    "get_current_user",
    "hasAccess",
    "security",
]
