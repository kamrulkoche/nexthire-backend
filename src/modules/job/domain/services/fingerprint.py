"""The cross-source duplicate key.

Two sources listing the same role rarely agree on ids, URLs or descriptions,
but they agree on the title, the company and roughly where. The fingerprint is
a hash of those three, normalized hard enough that "Senior Python Engineer
(Remote)" at "Acme, Inc." and "senior python engineer" at "ACME Inc" collide.

Deliberately conservative: two different roles at one company with one title
in one place WILL collide, and the later one is then hidden as a duplicate.
That is the right failure for a job board — the seeker still sees the role and
applies through the first copy — and it is far rarer than the reverse problem
of the same role showing three times.
"""

import hashlib
import re
from typing import Optional

_NOISE = re.compile(r"\((?:remote|hybrid|on-?site|m/w/d|f/m/d|m/f/d|w/m/d)\)", re.I)
_COMPANY_SUFFIX = re.compile(
    r"\b(inc|ltd|llc|gmbh|ag|plc|limited|corp|corporation|co|s\.?a)\b\.?", re.I
)
_NON_WORD = re.compile(r"[^a-z0-9]+")


def _normalize(value: Optional[str]) -> str:
    return _NON_WORD.sub(" ", (value or "").lower()).strip()


def job_fingerprint(title: str, company: str, location: Optional[str]) -> str:
    """Hash the parts of a posting that identify it across sources.

    Args:
        title: Job title
        company: Hiring company
        location: Free-text location, or None (remote postings often have none)

    Returns:
        A 64-character hex digest
    """
    clean_title = _normalize(_NOISE.sub(" ", title))
    clean_company = _normalize(_COMPANY_SUFFIX.sub(" ", company))
    # Only the first segment of a location: "Berlin, Germany" and "Berlin"
    # describe the same posting.
    clean_location = _normalize((location or "").split(",")[0])
    key = "|".join([clean_title, clean_company, clean_location])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
