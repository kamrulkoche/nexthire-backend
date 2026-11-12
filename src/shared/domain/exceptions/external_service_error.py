"""
External service error exception.

Raised when a third party this service depends on — Gemini, a job source —
fails or answers with something unusable.
"""

from .domain_exception import DomainException


class ExternalServiceError(DomainException):
    """
    A dependency outside this service failed.

    Mapped to 502 Bad Gateway: the request was fine and so is this service; the
    upstream was not. The message names the service but never echoes the
    upstream's body, which may carry a key in an error string.
    """

    def __init__(self, service: str, message: str = "The service did not respond."):
        """
        Initialize external service error.

        Args:
            service: Which dependency failed ("gemini", "remotive", ...)
            message: A safe, human-readable description
        """
        self.service = service
        super().__init__(f"{service}: {message}", {"service": service})
