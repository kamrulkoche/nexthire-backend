"""Use cases behind AI recommendations.

The pipeline, for one seeker:

1. SQL: visible, recent jobs not yet scored for them, narrowed by the hard
   constraints (``JobRepository.visible_candidates``)
2. Python: exclusions and keyword ranking (``prefilter.shortlist``) down to
   ``RECOMMENDATION_BATCH_SIZE``
3. The scorer: Gemini, or the heuristic — and the heuristic again if Gemini fails
4. Store one ``JobMatch`` per verdict

Two entry points share it: a seeker pressing Refresh
(``RefreshRecommendationsUseCase``) and a collection run announcing its new
jobs (``MatchNewJobsUseCase``), which also raises notifications.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import List, Optional, Sequence, Tuple
from uuid import UUID

from src.shared.infrastructure.database import MongoSession

from src.modules.job.application.services.job_presenter import JobPresenter
from src.modules.job.domain.enums.employment_type import EmploymentType
from src.modules.job.infrastructure.repositories.job_repository import JobRepository
from src.modules.notification.application.use_cases.notification_use_cases import (
    NotifyUseCase,
)
from src.modules.notification.domain.enums.notification_kind import NotificationKind
from src.modules.preference.domain.entities.job_preference import JobPreference
from src.modules.preference.infrastructure.repositories.preference_repository import (
    PreferenceRepository,
)
from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.external_service_error import ExternalServiceError
from src.shared.domain.exceptions.not_found_error import NotFoundError
from src.shared.domain.exceptions.validation_error import ValidationError
from src.shared.domain.time import utc_now
from src.shared.infrastructure.logging import get_logger
from src.shared.utils.config import settings

from ...domain.entities.job_match import JobMatch
from ...domain.services.job_scorer import (
    JobScorer,
    JobSnapshot,
    ScoredJob,
    SeekerProfile,
)
from ...domain.services.prefilter import shortlist
from ...infrastructure.repositories.job_match_repository import JobMatchRepository
from ...infrastructure.scorers.heuristic_scorer import (
    HEURISTIC_SCORER_NAME,
    HeuristicScorer,
)
from ..schemas.recommendation_schema import RecommendationSchema, RefreshResultSchema

logger = get_logger(__name__)

#: Only jobs posted (or first seen) within this window are recommended.
CANDIDATE_WINDOW_DAYS = 30

#: Most rows SQL hands the Python pre-filter.
CANDIDATE_LIMIT = 300


@dataclass
class _ScoringOutcome:
    matches: List[JobMatch]
    candidates: int
    scorer: str
    fallback_reason: Optional[str]


class _Matcher:
    """The shared pipeline."""

    def __init__(self, session: MongoSession, scorer: JobScorer) -> None:
        self.session = session
        self.scorer = scorer
        self.jobs = JobRepository(session)
        self.matches = JobMatchRepository(session)
        self.preferences = PreferenceRepository(session)

    async def _score_with_fallback(
        self, profile: SeekerProfile, snapshots: Sequence[JobSnapshot]
    ) -> Tuple[List[Tuple[ScoredJob, str]], Optional[str]]:
        """Score with the configured scorer, filling gaps with the heuristic.

        Returns:
            ``([(verdict, scorer_name), ...], fallback_reason)`` — each verdict
            carries the name of the scorer that actually produced it
        """
        if self.scorer.name == HEURISTIC_SCORER_NAME:
            verdicts = await self.scorer.score(profile, snapshots)
            return [(v, HEURISTIC_SCORER_NAME) for v in verdicts], None

        fallback_reason: Optional[str] = None
        try:
            ai_verdicts = await self.scorer.score(profile, snapshots)
        except ExternalServiceError as e:
            logger.warning(f"AI scoring failed, using the heuristic: {e.message}")
            ai_verdicts = []
            fallback_reason = "The AI scorer was unavailable."

        scored = [(v, self.scorer.name) for v in ai_verdicts]
        # Anything the AI did not answer for is scored by the heuristic, so a
        # shortlisted job is never silently skipped.
        answered = {v.job_id for v in ai_verdicts}
        rest = [s for s in snapshots if s.id not in answered]
        if rest:
            if fallback_reason is None:
                logger.info(
                    f"AI scorer skipped {len(rest)} job(s); heuristic filled in"
                )
            scored += [
                (v, HEURISTIC_SCORER_NAME)
                for v in await HeuristicScorer().score(profile, rest)
            ]
        return scored, fallback_reason

    async def score_for(
        self, prefs: JobPreference, *, only_job_ids: Optional[Sequence[UUID]] = None
    ) -> _ScoringOutcome:
        """Run the pipeline for one seeker and store the matches."""
        profile = SeekerProfile.from_preferences(prefs)
        employment_types = [
            EmploymentType(t)
            for t in prefs.employment_types
            if t in EmploymentType.all_types()
        ]
        candidates = await self.jobs.visible_candidates(
            since=utc_now() - timedelta(days=CANDIDATE_WINDOW_DAYS),
            exclude_ids=list(await self.matches.scored_job_ids(prefs.user_id)),
            remote_only=prefs.remote_only,
            employment_types=employment_types,
            only_ids=only_job_ids,
            limit=CANDIDATE_LIMIT,
        )
        snapshots = shortlist(
            profile,
            [JobSnapshot.from_job(job) for job in candidates],
            settings.recommendation_batch_size,
        )
        if not snapshots:
            return _ScoringOutcome([], len(candidates), self.scorer.name, None)

        scored, fallback_reason = await self._score_with_fallback(profile, snapshots)
        rows = [
            JobMatch(
                user_id=prefs.user_id,
                job_id=verdict.job_id,
                score=verdict.score,
                rationale=verdict.rationale,
                matched_skills=list(verdict.matched_skills),
                missing_skills=list(verdict.missing_skills),
                scorer=scorer_name,
                fallback_reason=fallback_reason,
            )
            for verdict, scorer_name in scored
        ]
        await self.matches.save_all(rows)
        used = HEURISTIC_SCORER_NAME if fallback_reason else self.scorer.name
        return _ScoringOutcome(rows, len(candidates), used, fallback_reason)


class RefreshRecommendationsUseCase(_Matcher):
    """A seeker asks for fresh recommendations."""

    async def execute(self, user_id: UUID) -> RefreshResultSchema:
        """Score the next batch of unscored jobs for the caller.

        Raises:
            ValidationError: The seeker has not saved preferences yet — there
                is nothing to score against
        """
        prefs = await self.preferences.get_for_user(user_id)
        if prefs is None:
            raise ValidationError(
                entity_name="JobPreference",
                field="preferences",
                message="Save your job preferences first.",
            )
        outcome = await self.score_for(prefs)
        return RefreshResultSchema(
            scored=len(outcome.matches),
            candidates=outcome.candidates,
            scorer=outcome.scorer,
            fallback_reason=outcome.fallback_reason,
        )


class MatchNewJobsUseCase(_Matcher):
    """A collection run announces new jobs; score them for everyone who asked."""

    async def execute(self, job_ids: Sequence[UUID]) -> int:
        """Score the new jobs for each seeker with notifications on.

        Never raises for one seeker's failure: a run's other seekers still get
        their matches.

        Returns:
            How many notifications were raised
        """
        if not job_ids:
            return 0
        notify = NotifyUseCase(self.session)
        raised = 0
        for prefs in await self.preferences.notifiable():
            try:
                outcome = await self.score_for(prefs, only_job_ids=job_ids)
                strong = [
                    m
                    for m in outcome.matches
                    if m.score >= settings.recommendation_notify_score
                ]
                if not strong:
                    continue
                best = max(strong, key=lambda m: m.score)
                count = len(strong)
                await notify.to_users(
                    [prefs.user_id],
                    kind=NotificationKind.NEW_MATCHES,
                    title=f"{count} new job{'s' if count != 1 else ''} match your preferences",
                    body=f"Best match scores {best.score}/100.",
                    link="/app/recommendations",
                )
                await self.matches.mark_notified([m.id for m in strong if m.id])
                raised += 1
            except Exception as e:
                logger.error(
                    f"Matching new jobs failed for one seeker: {e}", exc_info=True
                )
                self.session.rollback()
        return raised


class ListRecommendationsUseCase:
    """The caller's matches, best first."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.matches = JobMatchRepository(session)
        self.jobs = JobRepository(session)
        self.presenter = JobPresenter(session)

    async def execute(
        self,
        user_id: UUID,
        params: ListQueryParams,
        *,
        min_score: int = 0,
        include_dismissed: bool = False,
    ) -> Tuple[List[RecommendationSchema], int]:
        """List matches on jobs the caller can still see."""
        rows, total = await self.matches.list_for_user(
            user_id, params, min_score=min_score, include_dismissed=include_dismissed
        )
        jobs = await self.jobs.get_many(row.job_id for row in rows)
        ordered = [jobs[row.job_id] for row in rows if row.job_id in jobs]
        cards = {c.id: c for c in await self.presenter.summaries(ordered, user_id)}
        items = [
            RecommendationSchema(
                job=cards[row.job_id],
                score=row.score,
                rationale=row.rationale,
                matched_skills=list(row.matched_skills or []),
                missing_skills=list(row.missing_skills or []),
                scorer=row.scorer,
                is_ai=row.scorer != HEURISTIC_SCORER_NAME,
                is_dismissed=row.is_dismissed,
                scored_at=row.created_at,
            )
            for row in rows
            if row.job_id in cards
        ]
        return items, total


class DismissRecommendationUseCase:
    """Hide a match, or bring it back."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.session = session
        self.matches = JobMatchRepository(session)

    async def execute(self, user_id: UUID, job_id: UUID, dismissed: bool) -> None:
        """Set the flag on the caller's match.

        Raises:
            NotFoundError: The caller has no match for this job
        """
        match = await self.matches.get_for_user(user_id, job_id)
        if match is None:
            raise NotFoundError(entity_name="JobMatch", entity_id=job_id)
        match.is_dismissed = dismissed
        self.session.add(match)
        self.session.commit()
