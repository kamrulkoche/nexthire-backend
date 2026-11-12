"""Choosing a scorer.

Gemini when a key is configured, the heuristic otherwise. Routes get the
scorer through ``get_job_scorer`` (``api/dependencies.py``), so a test swaps it
for a fake without touching settings.
"""

from src.shared.infrastructure.ai.gemini_client import GeminiClient

from ...domain.services.job_scorer import JobScorer
from .gemini_scorer import GeminiScorer
from .heuristic_scorer import HeuristicScorer


def build_scorer() -> JobScorer:
    """The scorer this deployment should use."""
    client = GeminiClient()
    if client.is_configured:
        return GeminiScorer(client)
    return HeuristicScorer()
