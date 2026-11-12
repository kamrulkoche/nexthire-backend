"""Collection module dependencies for dependency injection."""

from fastapi import Depends
from src.shared.infrastructure.database import MongoSession

from src.shared.infrastructure.database import get_db

from ..application.use_cases.run_history_use_cases import GetRunUseCase, ListRunsUseCase
from ..application.use_cases.run_use_cases import StartRunUseCase


def get_start_run_use_case(db: MongoSession = Depends(get_db)) -> StartRunUseCase:
    """Get the start-run use case with the shared DB session."""
    return StartRunUseCase(db)


def get_list_runs_use_case(db: MongoSession = Depends(get_db)) -> ListRunsUseCase:
    """Get the run-history use case with the shared DB session."""
    return ListRunsUseCase(db)


def get_get_run_use_case(db: MongoSession = Depends(get_db)) -> GetRunUseCase:
    """Get the single-run use case with the shared DB session."""
    return GetRunUseCase(db)
