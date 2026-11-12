"""Lead Finder dependency injection.

``get_places_gateway_factory`` is the seam the integration suite overrides with
a fake, so no test calls Google.
"""

from fastapi import Depends
from src.shared.infrastructure.database import MongoSession

from src.shared.infrastructure.database import get_db

from ..application.use_cases.admin_use_cases import (
    GetLeadFinderSettingsUseCase,
    RegisterLeadFinderUseCase,
    RegistrationStatusUseCase,
    UpdateLeadFinderSettingsUseCase,
)
from ..application.use_cases.export_use_cases import (
    ExportLeadsUseCase,
    ListExportsUseCase,
)
from ..application.use_cases.lead_use_cases import (
    GetCatalogUseCase,
    GetLeadUseCase,
    LeadSummaryUseCase,
    ListLeadsUseCase,
    OverviewUseCase,
    RefreshLeadUseCase,
)
from ..application.use_cases.saved_lead_use_cases import (
    AddLeadNoteUseCase,
    DeleteLeadNoteUseCase,
    GetSavedLeadUseCase,
    ListSavedLeadsUseCase,
    SaveLeadsUseCase,
    UnsaveLeadUseCase,
    UpdateSavedLeadUseCase,
)
from ..application.use_cases.search_use_cases import (
    DeleteSearchUseCase,
    GatewayFactory,
    GetSearchUseCase,
    ListSearchesUseCase,
    RerunSearchUseCase,
    StartSearchUseCase,
    default_gateway_factory,
)


def get_places_gateway_factory() -> GatewayFactory:
    """How a use case gets a Places client. Tests return a fake."""
    return default_gateway_factory


def get_catalog_use_case(
    factory: GatewayFactory = Depends(get_places_gateway_factory),
) -> GetCatalogUseCase:
    """Catalog use case."""
    return GetCatalogUseCase(factory)


def get_overview_use_case(
    db: MongoSession = Depends(get_db),
    factory: GatewayFactory = Depends(get_places_gateway_factory),
) -> OverviewUseCase:
    """Overview use case."""
    return OverviewUseCase(db, factory)


def get_start_search_use_case(
    db: MongoSession = Depends(get_db),
    factory: GatewayFactory = Depends(get_places_gateway_factory),
) -> StartSearchUseCase:
    """Start-search use case."""
    return StartSearchUseCase(db, factory)


def get_rerun_search_use_case(
    db: MongoSession = Depends(get_db),
    factory: GatewayFactory = Depends(get_places_gateway_factory),
) -> RerunSearchUseCase:
    """Re-run use case."""
    return RerunSearchUseCase(db, factory)


def get_list_searches_use_case(
    db: MongoSession = Depends(get_db),
) -> ListSearchesUseCase:
    """Search history use case."""
    return ListSearchesUseCase(db)


def get_get_search_use_case(db: MongoSession = Depends(get_db)) -> GetSearchUseCase:
    """One-search use case."""
    return GetSearchUseCase(db)


def get_delete_search_use_case(
    db: MongoSession = Depends(get_db),
) -> DeleteSearchUseCase:
    """Delete-search use case."""
    return DeleteSearchUseCase(db)


def get_list_leads_use_case(db: MongoSession = Depends(get_db)) -> ListLeadsUseCase:
    """Lead list use case."""
    return ListLeadsUseCase(db)


def get_lead_summary_use_case(db: MongoSession = Depends(get_db)) -> LeadSummaryUseCase:
    """Lead summary use case."""
    return LeadSummaryUseCase(db)


def get_get_lead_use_case(db: MongoSession = Depends(get_db)) -> GetLeadUseCase:
    """One-lead use case."""
    return GetLeadUseCase(db)


def get_refresh_lead_use_case(
    db: MongoSession = Depends(get_db),
    factory: GatewayFactory = Depends(get_places_gateway_factory),
) -> RefreshLeadUseCase:
    """Refresh-lead use case."""
    return RefreshLeadUseCase(db, factory)


def get_save_leads_use_case(db: MongoSession = Depends(get_db)) -> SaveLeadsUseCase:
    """Save-leads use case."""
    return SaveLeadsUseCase(db)


def get_list_saved_leads_use_case(
    db: MongoSession = Depends(get_db),
) -> ListSavedLeadsUseCase:
    """Saved-leads list use case."""
    return ListSavedLeadsUseCase(db)


def get_get_saved_lead_use_case(
    db: MongoSession = Depends(get_db),
) -> GetSavedLeadUseCase:
    """One-saved-lead use case."""
    return GetSavedLeadUseCase(db)


def get_update_saved_lead_use_case(
    db: MongoSession = Depends(get_db),
) -> UpdateSavedLeadUseCase:
    """Saved-lead status use case."""
    return UpdateSavedLeadUseCase(db)


def get_unsave_lead_use_case(db: MongoSession = Depends(get_db)) -> UnsaveLeadUseCase:
    """Unsave use case."""
    return UnsaveLeadUseCase(db)


def get_add_note_use_case(db: MongoSession = Depends(get_db)) -> AddLeadNoteUseCase:
    """Add-note use case."""
    return AddLeadNoteUseCase(db)


def get_delete_note_use_case(
    db: MongoSession = Depends(get_db),
) -> DeleteLeadNoteUseCase:
    """Delete-note use case."""
    return DeleteLeadNoteUseCase(db)


def get_export_leads_use_case(db: MongoSession = Depends(get_db)) -> ExportLeadsUseCase:
    """Export use case."""
    return ExportLeadsUseCase(db)


def get_list_exports_use_case(db: MongoSession = Depends(get_db)) -> ListExportsUseCase:
    """Export history use case."""
    return ListExportsUseCase(db)


def get_lead_settings_use_case(
    db: MongoSession = Depends(get_db),
    factory: GatewayFactory = Depends(get_places_gateway_factory),
) -> GetLeadFinderSettingsUseCase:
    """Admin settings read use case."""
    return GetLeadFinderSettingsUseCase(db, factory)


def get_update_lead_settings_use_case(
    db: MongoSession = Depends(get_db),
    factory: GatewayFactory = Depends(get_places_gateway_factory),
) -> UpdateLeadFinderSettingsUseCase:
    """Admin settings update use case."""
    return UpdateLeadFinderSettingsUseCase(db, factory)


def get_registration_status_use_case(
    db: MongoSession = Depends(get_db),
) -> RegistrationStatusUseCase:
    """Public registration status use case."""
    return RegistrationStatusUseCase(db)


def get_register_lead_finder_use_case(
    db: MongoSession = Depends(get_db),
) -> RegisterLeadFinderUseCase:
    """Lead Finder registration use case."""
    return RegisterLeadFinderUseCase(db)
