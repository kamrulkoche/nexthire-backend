"""Job source module dependencies for dependency injection."""

from fastapi import Depends
from src.shared.infrastructure.database import MongoSession

from src.shared.infrastructure.database import get_db

from ..application.use_cases.job_source_use_cases import (
    CreateSourceUseCase,
    DeleteSourceUseCase,
    GetSourceUseCase,
    ListSourcesUseCase,
    UpdateSourceUseCase,
)


def get_list_sources_use_case(db: MongoSession = Depends(get_db)) -> ListSourcesUseCase:
    """Get the source list use case with the shared DB session."""
    return ListSourcesUseCase(db)


def get_get_source_use_case(db: MongoSession = Depends(get_db)) -> GetSourceUseCase:
    """Get the single-source use case with the shared DB session."""
    return GetSourceUseCase(db)


def get_create_source_use_case(
    db: MongoSession = Depends(get_db),
) -> CreateSourceUseCase:
    """Get the create-source use case with the shared DB session."""
    return CreateSourceUseCase(db)


def get_update_source_use_case(
    db: MongoSession = Depends(get_db),
) -> UpdateSourceUseCase:
    """Get the update-source use case with the shared DB session."""
    return UpdateSourceUseCase(db)


def get_delete_source_use_case(
    db: MongoSession = Depends(get_db),
) -> DeleteSourceUseCase:
    """Get the delete-source use case with the shared DB session."""
    return DeleteSourceUseCase(db)
