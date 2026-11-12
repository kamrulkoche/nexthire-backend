"""
Not found error exception.

Generic exception when any entity is not found.
"""

from typing import Any

from .domain_exception import DomainException


class NotFoundError(DomainException):
    """
    GENERIC exception when ANY entity is not found.

    Works for ALL entity types: User, Job, JobSource.
    """

    def __init__(self, entity_name: str, entity_id: Any):
        """
        Initialize not found error.

        Args:
            entity_name: Name of the entity (e.g., "Job")
            entity_id: ID that was not found
        """
        message = f"{entity_name} with ID '{entity_id}' not found"
        details = {"entity_name": entity_name, "entity_id": str(entity_id)}
        super().__init__(message, details)
