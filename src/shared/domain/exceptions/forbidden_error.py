"""
Forbidden error exception.

Generic exception for forbidden access / permission denied.
"""

from .domain_exception import DomainException


class ForbiddenError(DomainException):
    """
    GENERIC forbidden access error.

    Use when a user does not have permission to perform an action.
    """

    def __init__(
        self, message: str = "You do not have permission to perform this action."
    ):
        """
        Initialize forbidden error.

        Args:
            message: Description of why access is forbidden.
        """
        details = {"reason": message}
        super().__init__(message, details)
