"""
Already exists error exception.

Generic exception when creating an entity that violates a uniqueness rule.
"""

from typing import Any

from .domain_exception import DomainException


class AlreadyExistsError(DomainException):
    """
    GENERIC exception when an entity already exists.

    Works for ALL entity types and any unique field.
    """

    def __init__(self, entity_name: str, field: str, value: Any):
        """
        Initialize already exists error.

        Args:
            entity_name: Name of the entity (e.g., "Job")
            field: The unique field that collided
            value: The colliding value
        """
        message = f"{entity_name} with {field} '{value}' already exists"
        details = {"entity_name": entity_name, "field": field, "value": str(value)}
        super().__init__(message, details)
