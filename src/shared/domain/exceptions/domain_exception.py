"""
Base domain exception.

All domain exceptions inherit from this class.
"""

from typing import Optional


class DomainException(Exception):
    """
    Base exception for all domain-level errors.

    All domain exceptions inherit from this class to maintain
    a consistent exception hierarchy.
    """

    def __init__(
        self, message: str = "A domain error occurred", details: Optional[dict] = None
    ):
        """
        Initialize domain exception.

        Args:
            message: Error message
            details: Optional additional details
        """
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self):
        """Return string representation."""
        return self.message
