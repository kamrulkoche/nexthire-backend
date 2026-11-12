"""Saved job module dependencies for dependency injection."""

from fastapi import Depends
from src.shared.infrastructure.database import MongoSession

from src.shared.infrastructure.database import get_db

from ..application.use_cases.saved_job_use_cases import (
    ListSavedJobsUseCase,
    SaveJobUseCase,
    UnsaveJobUseCase,
)


def get_list_saved_jobs_use_case(
    db: MongoSession = Depends(get_db),
) -> ListSavedJobsUseCase:
    """Get the saved-jobs list use case with the shared DB session."""
    return ListSavedJobsUseCase(db)


def get_save_job_use_case(db: MongoSession = Depends(get_db)) -> SaveJobUseCase:
    """Get the save use case with the shared DB session."""
    return SaveJobUseCase(db)


def get_unsave_job_use_case(db: MongoSession = Depends(get_db)) -> UnsaveJobUseCase:
    """Get the unsave use case with the shared DB session."""
    return UnsaveJobUseCase(db)
