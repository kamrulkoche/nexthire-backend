"""Exporting leads, and the export history."""

from dataclasses import dataclass
from typing import List, Tuple
from uuid import UUID

from src.shared.infrastructure.database import MongoSession

from src.shared.application.schemas.pagination import ListQueryParams
from src.shared.domain.exceptions.not_found_error import NotFoundError
from src.shared.domain.exceptions.validation_error import ValidationError
from src.shared.domain.time import utc_now

from ...domain.entities.lead_export import LeadExport
from ...domain.enums import ExportFormat
from ...domain.value_objects.lead_filter import LeadFilter
from ...infrastructure.repositories.business_lead_repository import (
    BusinessLeadRepository,
)
from ...infrastructure.repositories.business_search_repository import (
    BusinessSearchRepository,
)
from ...infrastructure.repositories.lead_export_repository import LeadExportRepository
from ..schemas.lead_finder_schema import (
    MAX_EXPORT_ROWS,
    ExportRequestSchema,
    LeadExportSchema,
)
from ..services.lead_exporter import MEDIA_TYPES, build_export, file_name
from ..services.lead_presenter import LeadPresenter


@dataclass(frozen=True)
class ExportFile:
    """A produced file, ready to stream."""

    content: bytes
    file_name: str
    media_type: str
    row_count: int


class ExportLeadsUseCase:
    """Build an export file and record it in the history."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.leads = BusinessLeadRepository(session)
        self.searches = BusinessSearchRepository(session)
        self.exports = LeadExportRepository(session)
        self.presenter = LeadPresenter(session)

    async def execute(self, user_id: UUID, payload: ExportRequestSchema) -> ExportFile:
        """Produce the file.

        Raises:
            NotFoundError: The named search is not the caller's
            ValidationError: Nothing matches, or more rows than one file allows
        """
        title = "Business leads"
        prefix = "leads"
        if payload.search_id is not None:
            search = await self.searches.get_for_user(user_id, payload.search_id)
            if search is None:
                raise NotFoundError(
                    entity_name="BusinessSearch", entity_id=payload.search_id
                )
            title = f"{search.keyword} - {search.location_label}"
            prefix = f"leads-{search.keyword}"

        if payload.scope == "selection":
            filters = LeadFilter(lead_ids=list(payload.lead_ids))
        else:
            filters = LeadFilter(
                search_id=payload.search_id if payload.scope == "search" else None,
                website=payload.website,
                phone=payload.phone,
                min_rating=payload.min_rating,
                min_reviews=payload.min_reviews,
                division=payload.division,
                district=payload.district,
                category=payload.category,
                text=payload.text,
                saved=True if payload.scope == "saved" else None,
                duplicate_phone_only=payload.duplicates_only,
            )
            if payload.scope == "saved":
                title, prefix = "Saved leads", "saved-leads"

        rows, total = await self.leads.list_for_user(
            user_id,
            filters,
            offset=0,
            limit=MAX_EXPORT_ROWS + 1,
            sort="name",
            order="asc",
        )
        if total == 0:
            raise ValidationError(
                "LeadExport", "filters", "No leads match these filters."
            )
        if total > MAX_EXPORT_ROWS:
            raise ValidationError(
                "LeadExport",
                "filters",
                f"{total} leads match; one file holds at most {MAX_EXPORT_ROWS}. "
                "Narrow the filters.",
            )

        duplicates = await self.leads.duplicate_phones(user_id, filters.search_id)
        leads = await self.presenter.present(user_id, rows, duplicate_phones=duplicates)
        if payload.unique_phones:
            seen = set()
            unique = []
            for lead in leads:
                key = lead.phone_normalized or lead.phone
                if not key or key in seen:
                    continue
                seen.add(key)
                unique.append(lead)
            leads = unique

        now = utc_now()
        name = file_name(prefix, payload.format, now)
        content = build_export(payload.format, leads, title, now)

        recorded = filters.as_dict()
        if payload.unique_phones:
            recorded["unique_phones"] = True
        await self.exports.create(
            LeadExport(
                user_id=user_id,
                format=payload.format,
                scope=payload.scope,
                search_id=payload.search_id,
                row_count=len(leads),
                file_name=name,
                filters=recorded,
            )
        )
        return ExportFile(
            content=content,
            file_name=name,
            media_type=MEDIA_TYPES[ExportFormat(payload.format)],
            row_count=len(leads),
        )


class ListExportsUseCase:
    """The caller's export history."""

    def __init__(self, session: MongoSession) -> None:
        """Inject the database session."""
        self.exports = LeadExportRepository(session)

    async def execute(
        self, user_id: UUID, params: ListQueryParams
    ) -> Tuple[List[LeadExportSchema], int]:
        """A page of exports, newest first."""
        rows, total = await self.exports.list_for_user(user_id, params)
        return [LeadExportSchema.model_validate(row) for row in rows], total
