"""The cheap first pass before any job reaches a scorer.

SQL has already applied the structural filters (visible, recent, remote-only,
employment type, not yet scored). This pass applies the ones that need the
seeker's word lists, then ranks what is left by keyword relevance so that only
the most promising ``limit`` jobs are scored — the step that bounds what one
refresh can cost in Gemini calls.

Pure functions over snapshots; no I/O.
"""

import re
from typing import List, Sequence

from .job_scorer import JobSnapshot, SeekerProfile

_WORD = re.compile(r"[a-z0-9+#.]+")


def _contains(text: str, phrase: str) -> bool:
    """Whole-word, case-insensitive phrase match ("go" must not match "google")."""
    phrase = phrase.strip().lower()
    if not phrase:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def _haystacks(job: JobSnapshot) -> tuple[str, str, str]:
    return (
        job.title.lower(),
        " ".join(job.tags).lower(),
        job.description.lower(),
    )


def passes_hard_filters(profile: SeekerProfile, job: JobSnapshot) -> bool:
    """Whether the job survives the seeker's exclusions.

    - An excluded keyword in the title or tags rules the job out. The
      description is NOT checked: "no PHP experience needed" would otherwise
      exclude exactly the jobs a PHP-avoider wants.
    - With locations given, a non-remote job must name one of them.
    - A stated maximum salary below the seeker's minimum rules it out; an
      unstated salary does not.
    """
    title, tags, _ = _haystacks(job)
    for word in profile.excluded_keywords:
        if _contains(title, word) or _contains(tags, word):
            return False

    if profile.locations and not job.is_remote:
        location = (job.location or "").lower()
        if not any(place.lower() in location for place in profile.locations):
            return False

    if profile.min_salary and job.salary_max and job.salary_max < profile.min_salary:
        return False

    return True


def relevance(profile: SeekerProfile, job: JobSnapshot) -> float:
    """Keyword relevance in [0, 1]: how many keywords the job mentions, and where.

    A keyword in the title counts 3, in the tags 2, in the description 1, and
    the best placement wins. With no keywords every job scores 0.5 — the
    seeker has not told us what they want, so recency decides.
    """
    if not profile.keywords:
        return 0.5
    title, tags, description = _haystacks(job)
    placement = 0.0
    found = 0
    for keyword in profile.keywords:
        if _contains(title, keyword):
            placement += 3
        elif _contains(tags, keyword):
            placement += 2
        elif _contains(description, keyword):
            placement += 1
        else:
            continue
        found += 1
    # Coverage carries most of the weight: a posting that mentions every
    # keyword is relevant even if it mentions them only in its description.
    # Placement then separates the ones that lead with them.
    coverage = found / len(profile.keywords)
    return 0.7 * coverage + 0.3 * placement / (3 * len(profile.keywords))


def matched_keywords(profile: SeekerProfile, job: JobSnapshot) -> List[str]:
    """The seeker's keywords this job mentions anywhere."""
    title, tags, description = _haystacks(job)
    return [
        k
        for k in profile.keywords
        if _contains(title, k) or _contains(tags, k) or _contains(description, k)
    ]


def shortlist(
    profile: SeekerProfile, jobs: Sequence[JobSnapshot], limit: int
) -> List[JobSnapshot]:
    """The ``limit`` most relevant jobs that pass the hard filters.

    Ties keep the incoming order, which is newest first.
    """
    survivors = [job for job in jobs if passes_hard_filters(profile, job)]
    if profile.keywords:
        survivors = [job for job in survivors if relevance(profile, job) > 0]
    ranked = sorted(
        enumerate(survivors), key=lambda pair: (-relevance(profile, pair[1]), pair[0])
    )
    return [job for _, job in ranked[:limit]]
