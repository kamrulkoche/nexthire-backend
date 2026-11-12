"""Collection domain exceptions."""

from uuid import UUID

from src.shared.domain.exceptions.already_exists_error import AlreadyExistsError
from src.shared.domain.exceptions.domain_exception import DomainException


class RunInProgressError(AlreadyExistsError):
    """A run of this source already holds its claim.

    An ``AlreadyExistsError`` so the one handler file maps it to 409 — there
    IS already a run — with a message that says so plainly.
    """

    def __init__(self, source_id: UUID):
        """Initialize the error for one source."""
        DomainException.__init__(
            self,
            "This source is already being collected. Try again when the run finishes.",
            {
                "entity_name": "CollectionRun",
                "field": "source_id",
                "value": str(source_id),
            },
        )
