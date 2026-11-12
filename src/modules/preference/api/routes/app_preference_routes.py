"""
Job preferences — mounted at `/app/preferences`. The caller's own row only.
"""

from fastapi import APIRouter, Depends

from src.modules.user.domain.entities.user import User
from src.shared.api.auth.dependencies import SIGNED_IN, hasAccess

from ...application.schemas.preference_schema import (
    PreferenceSchema,
    PreferenceUpdateSchema,
)
from ...application.use_cases.preference_use_cases import (
    GetPreferencesUseCase,
    UpdatePreferencesUseCase,
)
from ..dependencies import (
    get_get_preferences_use_case,
    get_update_preferences_use_case,
)

router = APIRouter(tags=["Preferences"])


@router.get("", response_model=PreferenceSchema)
async def get_preferences(
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: GetPreferencesUseCase = Depends(get_get_preferences_use_case),
):
    """
    Read the caller's job preferences.

    **Access:** Any signed-in user. Never a 404: before the first save this
    returns the defaults with `exists: false`.
    """
    assert current_user.id is not None
    return await use_case.execute(current_user.id)


@router.put("", response_model=PreferenceSchema)
async def update_preferences(
    payload: PreferenceUpdateSchema,
    current_user: User = Depends(hasAccess(roles=SIGNED_IN)),
    use_case: UpdatePreferencesUseCase = Depends(get_update_preferences_use_case),
):
    """
    Replace the caller's job preferences.

    **Access:** Any signed-in user

    Clears the caller's undismissed AI matches, which were scored against the
    old preferences; the next refresh scores afresh.

    **Errors:**
    - 422 if a list has more than 20 entries or an entry is over 60 characters
    """
    assert current_user.id is not None
    return await use_case.execute(current_user.id, payload)
