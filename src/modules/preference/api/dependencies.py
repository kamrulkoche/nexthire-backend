"""Preference module dependencies for dependency injection."""

from fastapi import Depends
from src.shared.infrastructure.database import MongoSession

from src.shared.infrastructure.database import get_db

from ..application.use_cases.preference_use_cases import (
    GetPreferencesUseCase,
    UpdatePreferencesUseCase,
)


def get_get_preferences_use_case(
    db: MongoSession = Depends(get_db),
) -> GetPreferencesUseCase:
    """Get the read-preferences use case with the shared DB session."""
    return GetPreferencesUseCase(db)


def get_update_preferences_use_case(
    db: MongoSession = Depends(get_db),
) -> UpdatePreferencesUseCase:
    """Get the save-preferences use case with the shared DB session."""
    return UpdatePreferencesUseCase(db)
