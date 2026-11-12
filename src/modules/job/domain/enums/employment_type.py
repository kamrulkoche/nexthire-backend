"""Employment type enum."""

from enum import Enum


class EmploymentType(str, Enum):
    """
    The kind of engagement a posting offers.

    Sources spell this a dozen ways ("Full-Time", "full_time", "FULLTIME",
    "permanent"); ``from_source`` maps them onto this set at collection time so
    search filters on one vocabulary. Anything unrecognised becomes OTHER rather
    than null, so "we could not tell" is distinguishable from "not given".
    """

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    OTHER = "other"

    @classmethod
    def all_types(cls) -> list[str]:
        """Return all valid type values."""
        return [t.value for t in cls]

    @classmethod
    def from_source(cls, raw: object) -> "EmploymentType | None":
        """Map a source's spelling onto this enum.

        Args:
            raw: Whatever the source sent; None and blanks mean "not given"

        Returns:
            The matching member, OTHER for an unknown spelling, or None
        """
        if raw is None:
            return None
        text = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
        if not text:
            return None
        aliases = {
            "full_time": cls.FULL_TIME,
            "fulltime": cls.FULL_TIME,
            "permanent": cls.FULL_TIME,
            "part_time": cls.PART_TIME,
            "parttime": cls.PART_TIME,
            "contract": cls.CONTRACT,
            "contractor": cls.CONTRACT,
            "freelance": cls.CONTRACT,
            "internship": cls.INTERNSHIP,
            "intern": cls.INTERNSHIP,
            "working_student": cls.PART_TIME,
            "temporary": cls.TEMPORARY,
            "temp": cls.TEMPORARY,
        }
        return aliases.get(text, cls.OTHER)
