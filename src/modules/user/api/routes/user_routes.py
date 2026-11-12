"""
User admin API routes — the Users screen.

Admin only, every endpoint. There is no delete: an account that should stop
working is set `inactive`, which takes effect on that person's next request
and keeps their name on their saved jobs and applications.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.shared.api.auth.dependencies import ADMIN_ONLY, hasAccess
from src.shared.application.schemas.pagination import (
    ListQueryParams,
    PaginatedResponseSchema,
    list_query_params,
)

from ...application.schemas.user_schema import (
    UserCreateSchema,
    UserResponseSchema,
    UserUpdateSchema,
)
from ...application.use_cases.user_use_cases import (
    CreateUserUseCase,
    GetUserUseCase,
    ListUsersUseCase,
    UpdateUserUseCase,
)
from ...domain.entities.user import User
from ...domain.enums.user_role import UserRole
from ...domain.enums.user_status import UserStatus
from ..dependencies import (
    get_create_user_use_case,
    get_get_user_use_case,
    get_list_users_use_case,
    get_update_user_use_case,
)

router = APIRouter(tags=["Admin Users"])


@router.get("", response_model=PaginatedResponseSchema[UserResponseSchema])
async def list_users(
    role: Optional[UserRole] = Query(default=None, description="Narrow to one role"),
    status_filter: Optional[UserStatus] = Query(
        default=None, alias="status", description="Narrow to one account status"
    ),
    params: ListQueryParams = Depends(list_query_params),
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: ListUsersUseCase = Depends(get_list_users_use_case),
):
    """
    List accounts.

    **Access:** Admin only

    Searchable over name and email. Sort by `name`, `email`, `role`, `status`,
    `created_at` or `last_login_at`.
    """
    items, total = await use_case.execute(params, role=role, status=status_filter)
    return PaginatedResponseSchema.build(items, total, params)


@router.post("", response_model=UserResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateSchema,
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: CreateUserUseCase = Depends(get_create_user_use_case),
):
    """
    Add an account.

    **Access:** Admin only

    **Errors:**
    - 409 if the email is already in use
    - 422 if the password is under 12 characters or over 72 bytes
    """
    return await use_case.execute(payload)


@router.get("/{user_id}", response_model=UserResponseSchema)
async def get_user(
    user_id: UUID,
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: GetUserUseCase = Depends(get_get_user_use_case),
):
    """
    Read one account.

    **Access:** Admin only
    """
    return await use_case.execute(user_id)


@router.patch("/{user_id}", response_model=UserResponseSchema)
async def update_user(
    user_id: UUID,
    payload: UserUpdateSchema,
    current_user: User = Depends(hasAccess(roles=ADMIN_ONLY)),
    use_case: UpdateUserUseCase = Depends(get_update_user_use_case),
):
    """
    Update an account — details, role, status, or a password reset.

    **Access:** Admin only

    **Errors:**
    - 404 if no user has this ID
    - 422 if the change would leave no active admin
    """
    return await use_case.execute(user_id, payload)
