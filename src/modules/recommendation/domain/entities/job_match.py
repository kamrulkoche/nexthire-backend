"""
JobMatch entity — how well one job fits one seeker, and why.
"""

from typing import List, Optional
from uuid import UUID

from pydantic import Field, field_validator
from pymongo import ASCENDING, DESCENDING, IndexModel

from src.shared.domain.entities.base_entity import BaseEntity


class JobMatch(BaseEntity):
    """
    A scored (seeker, job) pair.

    Stored rather than computed per request because scoring can cost a Gemini
    call: a job is scored for a seeker once, and the score is re-used by every
    screen that shows it (recommendations, search cards, the dashboard).

    Scores are stale once the seeker changes their preferences, so saving
    preferences deletes their undismissed matches (``preference`` module) and
    the next refresh scores afresh. Dismissed matches survive, so a job the
    seeker said no to does not come back.

    Attributes:
        score: 0-100
        rationale: One or two sentences, plain text, shown on the card
        matched_skills / missing_skills: Short labels for the card's chips
        scorer: The model id that scored it, or ``heuristic``
        is_dismissed: The seeker hid it from their recommendations

    Collection: job_matches
    """

    __collection__ = "job_matches"
    __indexes__ = [
        IndexModel(
            [("user_id", ASCENDING), ("job_id", ASCENDING)],
            unique=True,
            name="uq_job_matches_user_job",
        ),
        IndexModel(
            [("user_id", ASCENDING), ("score", DESCENDING)],
            name="ix_job_matches_user_score",
        ),
        IndexModel([("job_id", ASCENDING)], name="ix_job_matches_job_id"),
    ]

    user_id: UUID

    job_id: UUID

    score: int

    rationale: str = Field(default="")

    matched_skills: List[str] = Field(default_factory=list)

    missing_skills: List[str] = Field(default_factory=list)

    scorer: str = Field(max_length=60)

    is_dismissed: bool = Field(default=False)

    notified: bool = Field(
        default=False,
        description="Already announced in a new-matches notification",
    )

    fallback_reason: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Why the AI scorer was not used, when it fell back",
    )

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: int) -> int:
        """0-100, as the old ``ck_job_matches_score`` CHECK constraint enforced."""
        if not 0 <= value <= 100:
            raise ValueError("score must be between 0 and 100")
        return value

    def __repr__(self) -> str:
        """String representation of JobMatch."""
        return f"<JobMatch(user_id='{self.user_id}', job_id='{self.job_id}', score={self.score})>"
