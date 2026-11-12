"""
Repository error exception.

Wraps any database-layer failure so callers never see a raw driver error.
"""

from .domain_exception import DomainException


class RepositoryError(DomainException):
    """
    GENERIC repository/database operation failure.

    Raised by repositories when an underlying SQLAlchemy or driver error
    occurs, preserving the original as the exception cause.
    """

    def __init__(self, entity_name: str, operation: str, message: str):
        """
        Initialize repository error.

        Args:
            entity_name: Entity the repository manages
            operation: Repository method that failed (e.g., "get_by_email")
            message: Underlying error text
        """
        full_message = f"{entity_name}.{operation} failed: {message}"
        details = {
            "entity_name": entity_name,
            "operation": operation,
            "reason": message,
        }
        super().__init__(full_message, details)
