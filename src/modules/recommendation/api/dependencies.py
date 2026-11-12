"""Recommendation module dependencies for dependency injection."""

from fastapi import Depends
from src.shared.infrastructure.database import MongoSession

from src.shared.infrastructure.database import get_db

from ..application.use_cases.recommendation_use_cases import (
    DismissRecommendationUseCase,
    ListRecommendationsUseCase,
    RefreshRecommendationsUseCase,
)
from ..domain.services.job_scorer import JobScorer
from ..infrastructure.scorers.factory import build_scorer


def get_job_scorer() -> JobScorer:
    """The scorer for this request. Tests override this with a fake."""
    return build_scorer()


def get_list_recommendations_use_case(
    db: MongoSession = Depends(get_db),
) -> ListRecommendationsUseCase:
    """Get the recommendations list use case with the shared DB session."""
    return ListRecommendationsUseCase(db)


def get_refresh_recommendations_use_case(
    db: MongoSession = Depends(get_db),
    scorer: JobScorer = Depends(get_job_scorer),
) -> RefreshRecommendationsUseCase:
    """Get the refresh use case with the shared DB session and the scorer."""
    return RefreshRecommendationsUseCase(db, scorer)


def get_dismiss_recommendation_use_case(
    db: MongoSession = Depends(get_db),
) -> DismissRecommendationUseCase:
    """Get the dismiss use case with the shared DB session."""
    return DismissRecommendationUseCase(db)
