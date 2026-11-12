"""
Self-service account routes — the app's Account settings screen.

Any signed-in user, acting on THEMSELVES only: every handler takes the
user `hasAccess` resolved from the session and never an id from the request.
Changing someone else's details, role or status stays on the admin-only Users
routes.
"""

from fastapi import APIRouter, Depends, Request

from src.shared.api.auth.dependencies import SIGNED_IN, hasAccess
from src.shared.infrastructure.security.rate_limiter import (
    enforce,
    password_change_limiter,
)

from ...application.schemas.account_schema import (
    AccountUpdateSchema,
    PasswordChangeResponseSchema,
    PasswordChangeSchema,
)
from ...application.schemas.user_schema import UserResponseSchema
from ...application.use_cases.account_use_cases import (
    ChangePasswordUseCase,
    UpdateAccountUseCase,
)
from ...domain.entities.user import User
from ..dependencies import get_change_password_use_case, get_update_account_use_case

router = APIRouter(tags=["Account"])


@router.get("", response_model=UserResponseSchema)
async def get_account(current_user: User = Depends(hasAccess(roles=SIGNED_IN))):
    """
    Read the caller's own profile.

    **Access:** Any signed-in user
    """
    return UserResponseSchema.model_validate(current_user)


@router.patch("", response_model=UserResponseSchema)
async def update_account(
    payload: AccountUpdateSchema,
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: UpdateAccountUseCase = Depends(get_update_account_use_case),
):
    """
    Change the caller's own name or phone number.

    **Access:** Any signed-in user. Role, status and email are not
    accepted here.

    **Errors:**
    - 422 if the name is under 2 characters
    """
    if current_user.id is None:
        raise ValueError("Authenticated user must have an ID")
    return await use_case.execute(current_user.id, payload)


@router.post("/password", response_model=PasswordChangeResponseSchema)
async def change_password(
    request: Request,
    payload: PasswordChangeSchema,
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: ChangePasswordUseCase = Depends(get_change_password_use_case),
):
    """
    Change the caller's own password.

    **Access:** Any signed-in user, who must supply the current password.

    **Errors:**
    - 422 if the current password is wrong (`current_password`), or the new one
      is under 12 characters, over 72 bytes, or the same as the current one
    - 429 after five attempts in fifteen minutes
    """
    if current_user.id is None:
        raise ValueError("Authenticated user must have an ID")
    key = f"user:{current_user.id}"
    enforce(password_change_limiter, key)
    result = await use_case.execute(current_user.id, payload)
    password_change_limiter.reset(key)
    return result
