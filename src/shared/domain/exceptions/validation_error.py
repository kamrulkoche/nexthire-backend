"""
Validation error exception.

Generic exception for domain-level validation failures.
"""

from .domain_exception import DomainException


class ValidationError(DomainException):
    """
    GENERIC validation error for ANY entity field.

    Raised by use cases when input violates a domain rule that Pydantic
    cannot express on its own.
    """

    def __init__(self, entity_name: str, field: str, message: str):
        """
        Initialize validation error.

        Args:
            entity_name: Name of the entity being validated
            field: Field that failed validation
            message: Why it failed
        """
        full_message = f"{entity_name}.{field}: {message}"
        details = {"entity_name": entity_name, "field": field, "reason": message}
        super().__init__(full_message, details)
