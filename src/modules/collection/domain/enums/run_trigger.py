"""Collection run trigger enum."""

from enum import Enum


class RunTrigger(str, Enum):
    """
    What started a run.

    - SCHEDULED: the scheduler found the source due
    - MANUAL: an admin pressed "Run now"
    """

    SCHEDULED = "scheduled"
    MANUAL = "manual"
