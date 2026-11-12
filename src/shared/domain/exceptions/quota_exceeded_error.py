"""
Quota exceeded exception.

Raised when a caller has spent a budget that is counted in the database rather
than by the in-process rate limiter: today, the Lead Finder's daily allowance
of Google Places requests.
"""

from typing import Optional

from .domain_exception import DomainException


class QuotaExceededError(DomainException):
    """
    A metered allowance is used up.

    Mapped to 429, like the rate limiter, because to the client it is the same
    answer: "not now". ``retry_after_seconds`` becomes the ``Retry-After``
    header when it is known.
    """

    def __init__(
        self,
        quota: str,
        message: str,
        *,
        limit: int,
        used: int,
        retry_after_seconds: Optional[int] = None,
    ):
        """
        Initialize the error.

        Args:
            quota: Which allowance ("places_daily", ...)
            message: Human-readable explanation for the screen
            limit: The allowance
            used: How much of it is spent
            retry_after_seconds: When it resets, if known
        """
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            message,
            {
                "quota": quota,
                "limit": limit,
                "used": used,
                "retry_after_seconds": retry_after_seconds,
            },
        )
