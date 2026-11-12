"""
Base entity class for the domain layer.

This module provides a minimal base class for entities that don't need
full audit tracking (created_by, updated_by, is_active).
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import ConfigDict, Field

from .document import MongoDocument


class BaseEntity(MongoDocument):
    """
    Minimal base class for domain entities.

    Provides only:
    - id: Unique identifier (UUID, stored as the document's ``_id``)
    - created_at: Creation timestamp

    For full audit tracking, use AuditedEntity instead.
    """

    id: UUID = Field(default_factory=uuid4, description="Unique identifier")

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp"
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "created_at": "2026-01-01T00:00:00Z",
            }
        },
    )
