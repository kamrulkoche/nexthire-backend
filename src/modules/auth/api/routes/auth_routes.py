"""
Authentication API routes: register, sign in, current profile, sign out.
"""

from fastapi import APIRouter, Depends, Request, status

from src.modules.user.application.schemas.user_schema import UserResponseSchema
from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import get_current_user
from src.shared.infrastructure.security.rate_limiter import (
    client_key,
    enforce,
    login_limiter,
    register_limiter,
)

from ...application.schemas.auth_schema import (
    LoginRequestSchema,
    LoginResponseSchema,
    LogoutResponseSchema,
    RegisterRequestSchema,
)
from ...application.use_cases.get_current_user_use_case import GetCurrentUserUseCase
from ...application.use_cases.login_use_case import LoginUseCase
from ...application.use_cases.logout_use_case import LogoutUseCase
from ...application.use_cases.register_use_case import RegisterUseCase
from ..dependencies import (
    get_get_current_user_use_case,
    get_login_use_case,
    get_logout_use_case,
    get_register_use_case,
)

router = APIRouter(tags=["Authentication"])


@router.post(
    "/login",
    response_model=LoginResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Sign in",
)
async def login(
    request: Request,
    credentials: LoginRequestSchema,
    use_case: LoginUseCase = Depends(get_login_use_case),
):
    """
    Authenticate with email and password.

    **Public endpoint** — rate limited to five attempts per fifteen minutes per
    (address, email). A successful sign-in clears the counter.

    **Errors:**
    - 401 if the credentials are wrong, or the account is not active
    - 422 if the email is malformed or the password is missing
    - 429 when the attempt budget is exhausted; `Retry-After` says how long
    """
    # Keyed on the email as well as the address, so one attacker cycling
    # addresses cannot lock a real user out of their own account.
    key = client_key(request, suffix=credentials.email.lower())
    enforce(login_limiter, key)

    result = await use_case.execute(credentials)

    # Only reached when the credentials were right.
    login_limiter.reset(key)
    return result


@router.post(
    "/register",
    response_model=LoginResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create a job seeker account",
)
async def register(
    request: Request,
    payload: RegisterRequestSchema,
    use_case: RegisterUseCase = Depends(get_register_use_case),
):
    """
    Create a job seeker account and sign it in.

    **Public endpoint** — rate limited to five accounts per hour per address.
    The response is the same as a login's, so the client is signed in at once.
    The new account is always a `seeker`; a `role` in the body is ignored.

    **Errors:**
    - 409 if the email is already registered
    - 422 if the password is under 12 characters or over 72 bytes
    - 429 when the address has registered too many accounts this hour
    """
    enforce(register_limiter, client_key(request))
    return await use_case.execute(payload)


@router.get(
    "/me",
    response_model=UserResponseSchema,
    summary="Get the signed-in user's profile",
)
async def get_me(
    current_user: User = Depends(get_current_user),
    use_case: GetCurrentUserUseCase = Depends(get_get_current_user_use_case),
):
    """
    Get the current user's profile.

    **Access:** Any signed-in user. Used by the frontend to confirm a session
    is still valid and to decide which dashboard items to show.
    """
    if current_user.id is None:
        raise ValueError("Authenticated user must have an ID")
    return await use_case.execute(current_user.id)


@router.post(
    "/logout",
    response_model=LogoutResponseSchema,
    summary="Sign out",
)
async def logout(
    current_user: User = Depends(get_current_user),
    use_case: LogoutUseCase = Depends(get_logout_use_case),
):
    """
    Sign the current user out.

    **Access:** Any signed-in user. The token is not revoked server-side in v1;
    the frontend clears its session cookie.
    """
    return await use_case.execute(current_user.email)
