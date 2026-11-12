"""Lead Finder domain exceptions."""

from src.shared.domain.exceptions.already_exists_error import AlreadyExistsError
from src.shared.domain.exceptions.domain_exception import DomainException
from src.shared.domain.exceptions.forbidden_error import ForbiddenError


class SearchInProgressError(AlreadyExistsError):
    """The caller already has a search queued or running.

    An ``AlreadyExistsError`` so the one handler file maps it to 409, as the
    collection module's ``RunInProgressError`` does.
    """

    def __init__(self) -> None:
        """Initialize with a message the screen can show as-is."""
        DomainException.__init__(
            self,
            "You already have a search running. Wait for it to finish, then "
            "start another.",
            {"entity_name": "BusinessSearch", "field": "status", "value": "running"},
        )


class RegistrationClosedError(ForbiddenError):
    """Lead Finder sign-up is switched off by an admin (403)."""

    def __init__(self) -> None:
        """Initialize with the reason."""
        DomainException.__init__(
            self,
            "Lead Finder registration is closed. Ask an administrator for an account.",
            {"entity_name": "User", "field": "registration", "value": "closed"},
        )
