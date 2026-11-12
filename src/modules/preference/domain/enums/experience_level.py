"""Experience level enum."""

from enum import Enum


class ExperienceLevel(str, Enum):
    """
    The seniority a seeker is looking for. Given to the scorer as context; it
    is not a hard filter, because sources rarely state seniority reliably.
    """

    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"

    @classmethod
    def all_levels(cls) -> list[str]:
        """Return all valid level values."""
        return [level.value for level in cls]
