"""
Unauthorized error exception.

Raised when authentication itself fails — bad credentials, or a token that is
missing, malformed or expired.

Ported from hgs-backend, which added it because — unlike sp-company-backend,
where Clerk owns the credential exchange — it owns login itself, so an
invalid-credentials failure originates in a USE CASE, and use cases must raise
domain exceptions rather than HTTP ones. NextHire AI owns login for the same
reason.
"""

from .domain_exception import DomainException


class UnauthorizedError(DomainException):
    """
    GENERIC authentication failure.

    The default message is deliberately vague. Distinguishing "no such email"
    from "wrong password" lets an attacker enumerate valid staff accounts, so
    both paths raise this identical error.
    """

    def __init__(self, message: str = "Invalid email or password."):
        """
        Initialize unauthorized error.

        Args:
            message: Description of the authentication failure.
        """
        details = {"reason": message}
        super().__init__(message, details)
