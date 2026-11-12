"""The single Lead Finder settings document."""

from typing import Type

from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from src.shared.domain.exceptions.repository_error import RepositoryError
from src.shared.infrastructure.base_repository import BaseRepository
from src.shared.infrastructure.database import MongoSession
from src.shared.utils.config import settings

from ...domain.entities.lead_finder_settings import LeadFinderSettings


class LeadFinderSettingsRepository(BaseRepository[LeadFinderSettings]):
    """Reads (creating on first use) and writes the settings document."""

    def __init__(
        self,
        session: MongoSession,
        model: Type[LeadFinderSettings] = LeadFinderSettings,
    ):
        """Initialize the settings repository."""
        super().__init__(session, model)

    async def get_or_create(self) -> LeadFinderSettings:
        """The settings document; created with defaults from config if absent.

        Always the OLDEST document, so a second one created by a race is
        ignored rather than making the settings flip between two values.
        """
        try:
            row = self.load(
                self.collection.find_one(
                    {}, sort=[("created_at", ASCENDING), ("_id", ASCENDING)]
                )
            )
            if row is not None:
                return row
        except Exception as e:
            raise RepositoryError(
                entity_name="LeadFinderSettings", operation="get", message=str(e)
            ) from e
        try:
            return await self.create(
                LeadFinderSettings(
                    registration_enabled=False,
                    daily_request_quota=settings.lead_daily_request_quota,
                    max_requests_per_search=settings.lead_max_requests_per_search,
                )
            )
        except (
            DuplicateKeyError
        ) as e:  # pragma: no cover - no unique field to collide on
            raise RepositoryError(
                entity_name="LeadFinderSettings", operation="create", message=str(e)
            ) from e
