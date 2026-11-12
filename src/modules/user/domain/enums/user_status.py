"""User account status enum."""

from enum import Enum


class UserStatus(str, Enum):
    """
    Account status enumeration, as in hgs-backend's AdminStatus.

    - ACTIVE: Account is usable and can sign in
    - INACTIVE: Account is disabled by an administrator
    - SUSPENDED: Account is temporarily blocked

    Only ACTIVE may authenticate; the other two are rejected at login and on
    every subsequent request, so disabling an account takes effect immediately
    rather than when their current token expires.
    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"

    @classmethod
    def all_statuses(cls) -> list[str]:
        """Return all valid status values."""
        return [status.value for status in cls]
