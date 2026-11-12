"""Application status enum."""

from enum import Enum


class ApplicationStatus(str, Enum):
    """
    Where a seeker's application stands. Free to move in any direction — a
    tracker records what happened, and real hiring loops go backwards.

    - INTERESTED: on the list, not applied yet
    - APPLIED: application sent
    - INTERVIEWING: in the interview loop
    - OFFER: offer received
    - HIRED: accepted
    - REJECTED: turned down by the employer
    - WITHDRAWN: the seeker pulled out
    """

    INTERESTED = "interested"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"

    @classmethod
    def all_statuses(cls) -> list[str]:
        """Return all valid status values."""
        return [status.value for status in cls]

    @property
    def is_open(self) -> bool:
        """Whether the application is still in play."""
        return self in {self.INTERESTED, self.APPLIED, self.INTERVIEWING, self.OFFER}
