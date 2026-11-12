"""
Lead Finder account settings — mounted at `/lead/account`.

The same self-service operations as `/app/account` (and the same use cases),
behind the Lead Finder role: lead finders cannot reach `/app/*` at all.
"""

from fastapi import APIRouter, Depends

from src.modules.user.api.dependencies import (
    get_change_password_use_case,
    get_update_account_use_case,
)
from src.modules.user.application.schemas.account_schema import (
    AccountUpdateSchema,
    PasswordChangeResponseSchema,
    PasswordChangeSchema,
)
from src.modules.user.application.schemas.user_schema import UserResponseSchema
from src.modules.user.application.use_cases.account_use_cases import (
    ChangePasswordUseCase,
    UpdateAccountUseCase,
)
from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import LEAD_FINDER_ONLY, hasAccess
from src.shared.infrastructure.security.rate_limiter import (
    enforce,
    password_change_limiter,
)

router = APIRouter(tags=["Lead Finder Account"])


@router.get("", response_model=UserResponseSchema)
async def get_account(current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY))):
    """The caller's own profile."""
    return UserResponseSchema.model_validate(current_user)


@router.patch("", response_model=UserResponseSchema)
async def update_account(
    payload: AccountUpdateSchema,
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: UpdateAccountUseCase = Depends(get_update_account_use_case),
):
    """Change the caller's own name or phone number."""
    assert current_user.id is not None
    return await use_case.execute(current_user.id, payload)


@router.post("/password", response_model=PasswordChangeResponseSchema)
async def change_password(
    payload: PasswordChangeSchema,
    current_user: User = Depends(hasAccess(roles=LEAD_FINDER_ONLY)),
    use_case: ChangePasswordUseCase = Depends(get_change_password_use_case),
):
    """
    Change the caller's own password (the current one is required).

    **Errors:** 422 for a wrong current password or a weak new one; 429 after
    five attempts in fifteen minutes.
    """
    assert current_user.id is not None
    key = f"user:{current_user.id}"
    enforce(password_change_limiter, key)
    result = await use_case.execute(current_user.id, payload)
    password_change_limiter.reset(key)
    return result
