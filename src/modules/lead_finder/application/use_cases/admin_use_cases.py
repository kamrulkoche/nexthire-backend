"""The admin side of Lead Finder, and its gated registration."""

from src.shared.infrastructure.database import MongoSession

from src.modules.auth.application.schemas.auth_schema import (
    LoginResponseSchema,
    RegisterRequestSchema,
)
from src.modules.auth.application.use_cases.register_use_case import RegisterUseCase
from src.modules.user.domain.entities.user import User
from src.modules.user.domain.enums.user_role import UserRole
from src.modules.user.infrastructure.repositories.user_repository import UserRepository
from src.shared.domain.time import utc_now
from src.shared.infrastructure.audit_context import get_current_user_id
from src.shared.utils.config import settings

from ...domain.exceptions import RegistrationClosedError
from ...infrastructure.repositories.business_lead_repository import (
    BusinessLeadRepository,
)
from ...infrastructure.repositories.business_search_repository import (
    BusinessSearchRepository,
)
from ...infrastructure.repositories.lead_finder_settings_repository import (
    LeadFinderSettingsRepository,
)
from ..schemas.lead_finder_schema import (
    LeadFinderSettingsSchema,
    LeadFinderSettingsUpdateSchema,
    RegistrationStatusSchema,
)
from .search_use_cases import GatewayFactory, default_gateway_factory


class _SettingsUseCase:
    def __init__(
        self,
        session: MongoSession,
        gateway_factory: GatewayFactory = default_gateway_factory,
    ) -> None:
        """Inject the session and the gateway factory."""
        self.session = session
        self.settings = LeadFinderSettingsRepository(session)
        self.searches = BusinessSearchRepository(session)
        self.leads = BusinessLeadRepository(session)
        self.gateway_factory = gateway_factory

    async def _present(self) -> LeadFinderSettingsSchema:
        row = await self.settings.get_or_create()
        day_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
        lead_finders = int(
            self.session.collection(User).count_documents(
                {"role": UserRole.LEAD_FINDER.value, "is_active": True}
            )
        )
        return LeadFinderSettingsSchema(
            registration_enabled=row.registration_enabled,
            daily_request_quota=row.daily_request_quota,
            max_requests_per_search=row.max_requests_per_search,
            updated_at=row.updated_at,
            places_configured=self.gateway_factory().is_configured,
            content_ttl_days=settings.lead_content_ttl_days,
            lead_finder_users=lead_finders,
            searches_today=await self.searches.count_since(day_start),
            requests_today=await self.searches.requests_since(day_start),
            leads_stored=await self.leads.count_all(),
        )


class GetLeadFinderSettingsUseCase(_SettingsUseCase):
    """The settings with today's usage."""

    async def execute(self) -> LeadFinderSettingsSchema:
        """Read (creating on first use)."""
        return await self._present()


class UpdateLeadFinderSettingsUseCase(_SettingsUseCase):
    """Change the settings. Omitted keys are left alone."""

    async def execute(
        self, payload: LeadFinderSettingsUpdateSchema
    ) -> LeadFinderSettingsSchema:
        """Apply the partial update."""
        row = await self.settings.get_or_create()
        for field, value in payload.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(row, field, value)
        row.updated_by = get_current_user_id()
        await self.settings.update(row)
        return await self._present()


class RegistrationStatusUseCase:
    """Whether the Lead Finder sign-up form is open."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.settings = LeadFinderSettingsRepository(session)

    async def execute(self) -> RegistrationStatusSchema:
        """Public: tells the frontend whether to show the form."""
        row = await self.settings.get_or_create()
        return RegistrationStatusSchema(registration_enabled=row.registration_enabled)


class RegisterLeadFinderUseCase:
    """Create a LEAD_FINDER account, if an admin has opened registration."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.settings = LeadFinderSettingsRepository(session)
        self.register = RegisterUseCase(
            UserRepository(session, User), role=UserRole.LEAD_FINDER
        )

    async def execute(self, payload: RegisterRequestSchema) -> LoginResponseSchema:
        """Create the account and sign it in.

        Raises:
            RegistrationClosedError: Registration is switched off (403)
            AlreadyExistsError: The email is taken (409)
        """
        if not (await self.settings.get_or_create()).registration_enabled:
            raise RegistrationClosedError()
        return await self.register.execute(payload)
