"""The keyword scorer — deterministic, offline, free.

Used when GEMINI_API_KEY is not set, and as the fallback when Gemini fails, so
recommendations always work. Its scores are honest about what they are: the
match is stored with ``scorer = "heuristic"`` and the frontend labels it.
"""

from typing import List, Sequence

from ...domain.services.job_scorer import JobSnapshot, ScoredJob, SeekerProfile
from ...domain.services.prefilter import matched_keywords, relevance

HEURISTIC_SCORER_NAME = "heuristic"


class HeuristicScorer:
    """Scores by keyword coverage, with small bonuses for location fit."""

    @property
    def name(self) -> str:
        """Stored on each match."""
        return HEURISTIC_SCORER_NAME

    async def score(
        self, profile: SeekerProfile, jobs: Sequence[JobSnapshot]
    ) -> List[ScoredJob]:
        """Score every job given.

        The base is keyword relevance scaled to 20-85; a remote job for a
        remote-only seeker and a location match each add 5. Capped at 95: a
        keyword count is never certain enough to claim a perfect match.
        """
        verdicts = []
        for job in jobs:
            base = 20 + relevance(profile, job) * 65
            reasons = []
            matched = matched_keywords(profile, job)
            if matched:
                reasons.append(f"Mentions {', '.join(matched[:4])}")
            if profile.remote_only and job.is_remote:
                base += 5
                reasons.append("remote")
            if profile.locations and job.location:
                if any(p.lower() in job.location.lower() for p in profile.locations):
                    base += 5
                    reasons.append(f"in {job.location}")
            if not reasons:
                reasons.append(
                    "Recent posting; add keywords to your preferences to rank by skills"
                )
            missing = [k for k in profile.keywords if k not in matched]
            verdicts.append(
                ScoredJob(
                    job_id=job.id,
                    score=max(0, min(95, round(base))),
                    rationale="; ".join(reasons) + ".",
                    matched_skills=matched[:8],
                    missing_skills=missing[:5],
                )
            )
        return verdicts
