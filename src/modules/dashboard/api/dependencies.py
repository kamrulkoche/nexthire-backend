"""Dashboard module dependencies for dependency injection."""

from fastapi import Depends
from src.shared.infrastructure.database import MongoSession

from src.shared.infrastructure.database import get_db

from ..application.use_cases.dashboard_use_cases import (
    GetAdminDashboardUseCase,
    GetSeekerDashboardUseCase,
)


def get_seeker_dashboard_use_case(
    db: MongoSession = Depends(get_db),
) -> GetSeekerDashboardUseCase:
    """Get the seeker dashboard use case with the shared DB session."""
    return GetSeekerDashboardUseCase(db)


def get_admin_dashboard_use_case(
    db: MongoSession = Depends(get_db),
) -> GetAdminDashboardUseCase:
    """Get the admin dashboard use case with the shared DB session."""
    return GetAdminDashboardUseCase(db)
