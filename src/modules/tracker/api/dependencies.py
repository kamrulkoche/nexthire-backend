"""Application module dependencies for dependency injection."""

from fastapi import Depends
from src.shared.infrastructure.database import MongoSession

from src.shared.infrastructure.database import get_db

from ..application.use_cases.application_use_cases import (
    ApplicationCountsUseCase,
    CreateApplicationUseCase,
    DeleteApplicationUseCase,
    GetApplicationUseCase,
    ListApplicationsUseCase,
    UpdateApplicationUseCase,
)


def get_list_applications_use_case(
    db: MongoSession = Depends(get_db),
) -> ListApplicationsUseCase:
    """Get the tracker list use case with the shared DB session."""
    return ListApplicationsUseCase(db)


def get_application_counts_use_case(
    db: MongoSession = Depends(get_db),
) -> ApplicationCountsUseCase:
    """Get the per-status counts use case with the shared DB session."""
    return ApplicationCountsUseCase(db)


def get_get_application_use_case(
    db: MongoSession = Depends(get_db),
) -> GetApplicationUseCase:
    """Get the single-application use case with the shared DB session."""
    return GetApplicationUseCase(db)


def get_create_application_use_case(
    db: MongoSession = Depends(get_db),
) -> CreateApplicationUseCase:
    """Get the create use case with the shared DB session."""
    return CreateApplicationUseCase(db)


def get_update_application_use_case(
    db: MongoSession = Depends(get_db),
) -> UpdateApplicationUseCase:
    """Get the update use case with the shared DB session."""
    return UpdateApplicationUseCase(db)


def get_delete_application_use_case(
    db: MongoSession = Depends(get_db),
) -> DeleteApplicationUseCase:
    """Get the delete use case with the shared DB session."""
    return DeleteApplicationUseCase(db)
