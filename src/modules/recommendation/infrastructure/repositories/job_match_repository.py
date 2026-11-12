"""
Job match repository.

As with saved jobs, every seeker-facing method filters on the caller's
``user_id``; there is no way to address another seeker's matches.

"On a job the seeker can still see" was a SQL join against ``jobs``; here it
is two queries — the caller's candidate job ids, then which of them pass
``visible_filter`` — which stays cheap because one seeker's matches are few.
"""

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Type
from uuid import UUID

from pymongo import DESCENDING

from src.modules.job.domain.entities.job import Job
from src.modules.job.infrastructure.repositories.job_repository import (
    visible_filter,
)
from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.repository_error import RepositoryError
from src.shared.infrastructure.base_repository import BaseRepository
from src.shared.infrastructure.database import MongoSession

from ...domain.entities.job_match import JobMatch


class JobMatchRepository(BaseRepository[JobMatch]):
    """Repository for JobMatch database operations."""

    def __init__(self, session: MongoSession, model: Type[JobMatch] = JobMatch):
        """Initialize the job match repository."""
        super().__init__(session, model)

    def _visible_job_ids(self, query: dict[str, Any]) -> List[UUID]:
        """Job ids of the matches ``query`` selects whose job is still visible."""
        job_ids = list(
            {d["job_id"] for d in self.collection.find(query, {"job_id": 1})}
        )
        if not job_ids:
            return []
        jobs = self.session.collection(Job)
        return [
            d["_id"]
            for d in jobs.find(
                {"_id": {"$in": job_ids}, **visible_filter()}, {"_id": 1}
            )
        ]

    async def scored_job_ids(self, user_id: UUID) -> Set[UUID]:
        """Every job already scored for this seeker, dismissed ones included."""
        try:
            return {
                d["job_id"]
                for d in self.collection.find({"user_id": user_id}, {"job_id": 1})
            }
        except Exception as e:
            raise RepositoryError(
                entity_name="JobMatch", operation="scored_job_ids", message=str(e)
            ) from e

    async def scores_for(
        self, user_id: UUID, job_ids: Iterable[UUID]
    ) -> Dict[UUID, int]:
        """The caller's scores for these jobs — to put on search cards."""
        ids = list(set(job_ids))
        if not ids:
            return {}
        try:
            cursor = self.collection.find(
                {"user_id": user_id, "job_id": {"$in": ids}},
                {"job_id": 1, "score": 1},
            )
            return {d["job_id"]: int(d["score"]) for d in cursor}
        except Exception as e:
            raise RepositoryError(
                entity_name="JobMatch", operation="scores_for", message=str(e)
            ) from e

    async def list_for_user(
        self,
        user_id: UUID,
        params: ListQueryParams,
        *,
        min_score: int = 0,
        include_dismissed: bool = False,
    ) -> Tuple[List[JobMatch], int]:
        """The caller's matches on jobs they can still see, best first."""
        try:
            query: dict[str, Any] = {"user_id": user_id, "score": {"$gte": min_score}}
            if not include_dismissed:
                query["is_dismissed"] = False
            query["job_id"] = {"$in": self._visible_job_ids(query)}
            total = self.collection.count_documents(query)
            cursor = (
                self.collection.find(query)
                .sort([("score", DESCENDING), ("created_at", DESCENDING)])
                .skip(params.offset)
                .limit(params.limit)
            )
            return self.load_many(cursor), int(total)
        except Exception as e:
            raise RepositoryError(
                entity_name="JobMatch", operation="list_for_user", message=str(e)
            ) from e

    async def get_for_user(self, user_id: UUID, job_id: UUID) -> Optional[JobMatch]:
        """The caller's match on this job, or None."""
        try:
            return self.load(
                self.collection.find_one({"user_id": user_id, "job_id": job_id})
            )
        except Exception as e:
            raise RepositoryError(
                entity_name="JobMatch", operation="get_for_user", message=str(e)
            ) from e

    async def save_all(self, matches: Sequence[JobMatch]) -> None:
        """Insert or update a batch of matches in one commit."""
        if not matches:
            return
        try:
            self.session.add_all(list(matches))
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            raise RepositoryError(
                entity_name="JobMatch", operation="save_all", message=str(e)
            ) from e

    async def clear_undismissed(self, user_id: UUID) -> int:
        """Drop a seeker's live matches after their preferences change."""
        try:
            result = self.collection.delete_many(
                {"user_id": user_id, "is_dismissed": False}
            )
            return int(result.deleted_count)
        except Exception as e:
            raise RepositoryError(
                entity_name="JobMatch", operation="clear_undismissed", message=str(e)
            ) from e

    async def mark_notified(self, match_ids: Sequence[UUID]) -> None:
        """Record that these matches were announced."""
        if not match_ids:
            return
        try:
            self.collection.update_many(
                {"_id": {"$in": list(match_ids)}}, {"$set": {"notified": True}}
            )
        except Exception as e:
            raise RepositoryError(
                entity_name="JobMatch", operation="mark_notified", message=str(e)
            ) from e

    async def count_strong(self, user_id: UUID, min_score: int) -> int:
        """Undismissed matches at or above ``min_score`` on visible jobs."""
        try:
            query: dict[str, Any] = {
                "user_id": user_id,
                "score": {"$gte": min_score},
                "is_dismissed": False,
            }
            query["job_id"] = {"$in": self._visible_job_ids(query)}
            return int(self.collection.count_documents(query))
        except Exception as e:
            raise RepositoryError(
                entity_name="JobMatch", operation="count_strong", message=str(e)
            ) from e
