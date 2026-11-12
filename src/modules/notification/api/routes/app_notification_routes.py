"""
Notifications — mounted at `/app/notifications`. The caller's own only.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import SIGNED_IN, hasAccess
from src.shared.application.schemas.pagination import (
    ListQueryParams,
    PaginatedResponseSchema,
    list_query_params,
)

from ...application.schemas.notification_schema import (
    MarkedReadSchema,
    NotificationSchema,
    UnreadCountSchema,
)
from ...application.use_cases.notification_use_cases import (
    ListNotificationsUseCase,
    MarkAllReadUseCase,
    MarkReadUseCase,
    UnreadCountUseCase,
)
from ..dependencies import (
    get_list_notifications_use_case,
    get_mark_all_read_use_case,
    get_mark_read_use_case,
    get_unread_count_use_case,
)

router = APIRouter(tags=["Notifications"])


@router.get("", response_model=PaginatedResponseSchema[NotificationSchema])
async def list_notifications(
    unread_only: bool = Query(default=False, description="Only unread ones"),
    params: ListQueryParams = Depends(list_query_params),
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: ListNotificationsUseCase = Depends(get_list_notifications_use_case),
):
    """
    List the caller's notifications, newest first.

    **Access:** Any signed-in user
    """
    assert current_user.id is not None
    items, total = await use_case.execute(
        current_user.id, params, unread_only=unread_only
    )
    return PaginatedResponseSchema.build(items, total, params)


@router.get("/unread-count", response_model=UnreadCountSchema)
async def unread_count(
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: UnreadCountUseCase = Depends(get_unread_count_use_case),
):
    """
    Count the caller's unread notifications — the bell's badge.

    **Access:** Any signed-in user. Declared before `/{notification_id}`.
    """
    assert current_user.id is not None
    return await use_case.execute(current_user.id)


@router.post("/read-all", response_model=MarkedReadSchema)
async def mark_all_read(
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: MarkAllReadUseCase = Depends(get_mark_all_read_use_case),
):
    """
    Mark every notification read.

    **Access:** Any signed-in user
    """
    assert current_user.id is not None
    return await use_case.execute(current_user.id)


@router.patch("/{notification_id}/read", response_model=NotificationSchema)
async def mark_read(
    notification_id: UUID,
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: MarkReadUseCase = Depends(get_mark_read_use_case),
):
    """
    Mark one notification read.

    **Access:** Any signed-in user, own notifications only

    **Errors:**
    - 404 if the caller has no notification with this id
    """
    assert current_user.id is not None
    return await use_case.execute(current_user.id, notification_id)
