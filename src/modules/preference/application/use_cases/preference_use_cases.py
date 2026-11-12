"""Use cases behind the Preferences screen."""

from uuid import UUID

from src.shared.infrastructure.database import MongoSession

from src.modules.recommendation.infrastructure.repositories.job_match_repository import (
    JobMatchRepository,
)
from src.shared.domain.time import utc_now
from src.shared.infrastructure.logging import get_logger

from ...domain.entities.job_preference import JobPreference
from ...infrastructure.repositories.preference_repository import PreferenceRepository
from ..schemas.preference_schema import PreferenceSchema, PreferenceUpdateSchema

logger = get_logger(__name__)


def to_schema(row: JobPreference) -> PreferenceSchema:
    """A stored row as the screen receives it."""
    return PreferenceSchema.model_validate(row).model_copy(update={"exists": True})


class GetPreferencesUseCase:
    """Read the caller's preferences."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.repository = PreferenceRepository(session)

    async def execute(self, user_id: UUID) -> PreferenceSchema:
        """The stored preferences, or the defaults with ``exists: false``.

        Not a 404 when absent: every seeker HAS preferences, they have just not
        changed the defaults yet, and the form needs something to render.
        """
        row = await self.repository.get_for_user(user_id)
        if row is None:
            return PreferenceSchema(exists=False)
        return to_schema(row)


class UpdatePreferencesUseCase:
    """Replace the caller's preferences."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session.

        Args:
            session: Active database session
        """
        self.session = session
        self.repository = PreferenceRepository(session)
        self.matches = JobMatchRepository(session)

    async def execute(
        self, user_id: UUID, payload: PreferenceUpdateSchema
    ) -> PreferenceSchema:
        """Upsert the row, then drop the seeker's stale matches.

        Every score was computed against the OLD preferences, so they are
        cleared and the next refresh scores afresh. Dismissed matches are kept,
        so a job the seeker turned down does not come back.
        """
        values = payload.model_dump()
        values["employment_types"] = [t.value for t in payload.employment_types]

        row = await self.repository.get_for_user(user_id)
        if row is None:
            row = JobPreference(user_id=user_id, created_by=user_id, **values)
            row = await self.repository.create(row)
        else:
            for key, value in values.items():
                setattr(row, key, value)
            row.updated_by = user_id
            row.updated_at = utc_now()
            self.session.add(row)
            self.session.commit()
            self.session.refresh(row)

        cleared = await self.matches.clear_undismissed(user_id)
        if cleared:
            logger.info(f"Cleared {cleared} stale matches after a preference change")
        return to_schema(row)
