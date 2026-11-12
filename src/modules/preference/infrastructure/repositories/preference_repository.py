"""Job preference repository. Keyed by the caller's ``user_id`` throughout."""

from typing import List, Optional, Type
from uuid import UUID

from src.modules.user.domain.entities.user import User
from src.modules.user.domain.enums.user_status import UserStatus
from src.shared.domain.exceptions.repository_error import RepositoryError
from src.shared.infrastructure.base_repository import BaseRepository
from src.shared.infrastructure.database import MongoSession

from ...domain.entities.job_preference import JobPreference


class PreferenceRepository(BaseRepository[JobPreference]):
    """Repository for JobPreference database operations."""

    def __init__(
        self, session: MongoSession, model: Type[JobPreference] = JobPreference
    ):
        """Initialize the preference repository."""
        super().__init__(session, model)

    async def get_for_user(self, user_id: UUID) -> Optional[JobPreference]:
        """The caller's preferences, or None if never saved."""
        try:
            return self.load(self.collection.find_one({"user_id": user_id}))
        except Exception as e:
            raise RepositoryError(
                entity_name="JobPreference", operation="get_for_user", message=str(e)
            ) from e

    async def notifiable(self) -> List[JobPreference]:
        """Preferences of users who want match notifications and can sign in.

        Used after a collection run to score its new jobs for each of them.
        Two queries instead of a join: the preferences, then which of their
        owners can still sign in.
        """
        try:
            rows = self.load_many(self.collection.find({"notify_on_match": True}))
            if not rows:
                return []
            active = {
                doc["_id"]
                for doc in self.session.collection(User).find(
                    {
                        "_id": {"$in": [r.user_id for r in rows]},
                        "is_active": True,
                        "status": UserStatus.ACTIVE.value,
                    },
                    {"_id": 1},
                )
            }
            return [r for r in rows if r.user_id in active]
        except Exception as e:
            raise RepositoryError(
                entity_name="JobPreference", operation="notifiable", message=str(e)
            ) from e
