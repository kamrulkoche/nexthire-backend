"""
Audited entity class for the domain layer.

This module provides the base class with common auditing fields for all domain entities.
"""

from datetime import UTC, datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import ConfigDict, Field

from .document import MongoDocument


class AuditedEntity(MongoDocument):
    """
    Base class for all domain entities with common auditing fields.

    All entities inherit the following fields:
    - id: Unique identifier (UUID, stored as the document's ``_id``)
    - is_active: Soft delete flag
    - created_at: Creation timestamp
    - updated_at: Last update timestamp
    - created_by: User who created the record
    - updated_by: User who last updated the record

    ``created_by`` / ``updated_by`` are plain nullable UUIDs recording who
    acted; MongoDB enforces no reference between documents.
    """

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")

    is_active: bool = Field(
        default=True, description="Soft delete flag - False means deleted"
    )

    created_by: Optional[UUID] = Field(
        default=None, description="User who created this record"
    )
    updated_by: Optional[UUID] = Field(
        default=None, description="User who last updated this record"
    )

    # UTC instants. MongoDB stores milliseconds; the client returns them
    # tz-aware (see shared/infrastructure/database.get_client).
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Last update timestamp"
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "is_active": True,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        },
    )
