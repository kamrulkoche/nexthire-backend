"""
Lead Finder sign-in and sign-up. Mounted at `/auth/lead-finder`.

A separate sign-in from `/auth/login`: it issues sessions ONLY to lead finders,
and the main sign-in refuses them, so the two products never share a session.
`/auth/me` and `/auth/logout` serve both.
"""

from fastapi import APIRouter, Depends, Request, status

from src.modules.auth.api.dependencies import get_user_repository
from src.modules.auth.application.schemas.auth_schema import (
    LoginRequestSchema,
    LoginResponseSchema,
    RegisterRequestSchema,
)
from src.modules.auth.application.use_cases.login_use_case import (
    LEAD_FINDER_ROLES,
    LoginUseCase,
)
from src.modules.user.infrastructure.repositories.user_repository import UserRepository
from src.shared.infrastructure.security.rate_limiter import (
    client_key,
    enforce,
    login_limiter,
    register_limiter,
)

from ...application.schemas.lead_finder_schema import RegistrationStatusSchema
from ...application.use_cases.admin_use_cases import (
    RegisterLeadFinderUseCase,
    RegistrationStatusUseCase,
)
from ..dependencies import (
    get_register_lead_finder_use_case,
    get_registration_status_use_case,
)

router = APIRouter(tags=["Lead Finder Authentication"])


def get_lead_login_use_case(
    repository: UserRepository = Depends(get_user_repository),
) -> LoginUseCase:
    """A login that accepts lead finders only."""
    return LoginUseCase(
        repository,
        allowed_roles=LEAD_FINDER_ROLES,
        wrong_portal_message=(
            "This is a NextHire AI job account. Sign in at /login instead."
        ),
    )


@router.post("/login", response_model=LoginResponseSchema)
async def lead_login(
    request: Request,
    credentials: LoginRequestSchema,
    use_case: LoginUseCase = Depends(get_lead_login_use_case),
):
    """
    Sign in to Lead Finder.

    **Public endpoint** — shares the main sign-in's limiter (five attempts per
    fifteen minutes per address and email).

    **Errors:**
    - 401 for wrong credentials, an inactive account, or a non-Lead-Finder account
    - 429 when the attempt budget is spent
    """
    key = client_key(request, suffix=credentials.email.lower())
    enforce(login_limiter, key)
    result = await use_case.execute(credentials)
    login_limiter.reset(key)
    return result


@router.post(
    "/register", response_model=LoginResponseSchema, status_code=status.HTTP_201_CREATED
)
async def lead_register(
    request: Request,
    payload: RegisterRequestSchema,
    use_case: RegisterLeadFinderUseCase = Depends(get_register_lead_finder_use_case),
):
    """
    Create a Lead Finder account and sign it in — only while an admin has
    registration switched on.

    **Errors:**
    - 403 when registration is closed
    - 409 if the email is already registered (in either product)
    - 422 if the password is under 12 characters or over 72 bytes
    - 429 when the address has registered too many accounts this hour
    """
    enforce(register_limiter, client_key(request))
    return await use_case.execute(payload)


@router.get("/status", response_model=RegistrationStatusSchema)
async def lead_registration_status(
    use_case: RegistrationStatusUseCase = Depends(get_registration_status_use_case),
):
    """Whether Lead Finder registration is open. **Public.**"""
    return await use_case.execute()
